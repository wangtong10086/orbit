"""Core remote-machine commands for the remote_ops sidecar."""

from __future__ import annotations

import os

import click

from forge.remote_ops.service import get_rental, run_async
from forge.training.templates import load_template

_SYNC_PATHS = ["scripts/", "forge/", "knowledge/", "experiments/"]
_REMOTE_BASE = "/root/project"


def _machine_selector(ctx) -> str | None:
    return ctx.parent.params.get("machine")


@click.command()
@click.pass_context
def status(ctx):
    """Show rental GPU, processes, and training status."""

    config = ctx.obj["config"]
    backend, inst = get_rental(config, _machine_selector(ctx))

    async def _run():
        health = await backend.health_check(inst)
        click.echo(f"\n=== {inst.id} ({inst.host}) ===")
        click.echo(f"Status: {health.get('status', '?')}")

        if health.get("gpu_info"):
            click.echo("\nGPU:")
            for line in health["gpu_info"]:
                click.echo(f"  {line.strip()}")

        click.echo(f"Disk free: {health.get('disk_free', '?')}")
        click.echo(f"Training: {health.get('training', '?')}")
        click.echo(f"Checkpoint: {health.get('latest_checkpoint', 'none')}")

        rc, out, _ = await backend.exec(inst, "screen -ls 2>/dev/null || true", timeout=10)
        if rc == 0 and out.strip():
            click.echo(f"\nScreens:\n{out.strip()}")

    run_async(_run())


@click.command(name="exec")
@click.argument("command")
@click.option("--timeout", default=60, type=int, help="Timeout in seconds")
@click.pass_context
def machine_exec(ctx, command, timeout):
    """Execute a command on the rental machine."""

    config = ctx.obj["config"]
    backend, inst = get_rental(config, _machine_selector(ctx))

    async def _run():
        rc, stdout, stderr = await backend.exec(inst, command, timeout=timeout)
        if stdout:
            click.echo(stdout.rstrip())
        if stderr:
            click.echo(stderr.rstrip(), err=True)
        if rc != 0:
            raise SystemExit(rc)

    run_async(_run())


@click.command()
@click.argument("process", type=click.Choice(["sglang", "eval", "training", "all"]))
@click.pass_context
def kill(ctx, process):
    """Kill a process on the rental machine."""

    config = ctx.obj["config"]
    backend, inst = get_rental(config, _machine_selector(ctx))
    kill_cmds = {
        "sglang": "pkill -9 -f sglang; screen -S sglang -X quit 2>/dev/null",
        "eval": "pkill -9 -f eval_envs; screen -S eval -X quit 2>/dev/null",
        "training": "pkill -9 -f train; screen -S train -X quit 2>/dev/null",
        "all": "pkill -9 -f sglang; pkill -9 -f eval_envs; pkill -9 -f train; screen -wipe 2>/dev/null",
    }

    async def _run():
        click.echo(f"Killing {process}...")
        await backend.exec(inst, kill_cmds[process], timeout=15)
        rc, out, _ = await backend.exec(
            inst,
            "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader",
            timeout=15,
        )
        if rc == 0:
            click.echo("\nGPU after kill:")
            for line in out.strip().split("\n"):
                click.echo(f"  {line.strip()}")

    run_async(_run())


@click.command(name="start-training")
@click.argument("script_path")
@click.option("--tp", default=4, type=int, help="Tensor parallel degree")
@click.pass_context
def start_training(ctx, script_path, tp):
    """Start training on rental in a detached screen session."""

    config = ctx.obj["config"]
    backend, inst = get_rental(config, _machine_selector(ctx))

    async def _run():
        remote_script = f"/root/scripts/{os.path.basename(script_path)}"
        click.echo(f"Uploading {script_path} -> {remote_script}")
        await backend.upload(inst, script_path, remote_script)

        train_cmd = (
            "screen -dmS train bash -c '"
            "source /root/venv/bin/activate && "
            "source /root/.env && "
            "cd /root && "
            f"python3 {remote_script} 2>&1 | tee /root/logs/train.log'"
        )
        click.echo("Starting training in screen 'train'...")
        rc, _, err = await backend.exec(inst, train_cmd, timeout=15)
        if rc != 0:
            raise click.ClickException(f"Failed to start: {err}")
        click.echo("Training started. Monitor with: forge remote machine status")

    run_async(_run())


@click.command(name="upload")
@click.argument("local_path")
@click.argument("remote_path")
@click.pass_context
def upload_file(ctx, local_path, remote_path):
    """Upload a local file or dir to the rental machine."""

    config = ctx.obj["config"]
    backend, inst = get_rental(config, _machine_selector(ctx))

    async def _run():
        click.echo(f"Uploading {local_path} -> {remote_path}")
        await backend.upload(inst, local_path, remote_path)
        click.echo("Done.")

    run_async(_run())


@click.command(name="transfer")
@click.argument("source_machine")
@click.argument("remote_path")
@click.option("--dest-path", default=None, help="Destination path (default: same as source)")
@click.pass_context
def transfer(ctx, source_machine, remote_path, dest_path):
    """Transfer a file or dir between machines via local relay."""

    import tempfile

    config = ctx.obj["config"]
    backend, src_inst = get_rental(config, source_machine)
    _, dst_inst = get_rental(config, _machine_selector(ctx))
    dst = dest_path or remote_path

    async def _run():
        with tempfile.TemporaryDirectory() as tmp:
            click.echo(f"{src_inst.id}:{remote_path} -> {dst_inst.id}:{dst}")
            await backend.download(src_inst, remote_path, f"{tmp}/")
            await backend.upload(dst_inst, f"{tmp}/", os.path.dirname(dst) + "/")
            click.echo("Done.")

    run_async(_run())


@click.command(name="monitor")
@click.pass_context
def monitor(ctx):
    """Show training progress: step, loss, GPU, ETA."""

    config = ctx.obj["config"]
    backend, inst = get_rental(config, _machine_selector(ctx))

    def _clean(text):
        return "\n".join(
            line for line in text.strip().split("\n") if not line.strip().startswith("Connecting to")
        ).strip()

    async def _run():
        monitor_script = load_template("monitor_rental.sh")
        rc, out, _ = await backend.exec(inst, monitor_script, timeout=20)
        if rc == 0:
            click.echo(_clean(out))
            return
        rc, out, _ = await backend.exec(inst, "tail -5 /root/training.log 2>/dev/null", timeout=10)
        if rc == 0:
            click.echo(f"\nLast log:\n{_clean(out)}")

    run_async(_run())


@click.command(name="sync")
@click.option("--paths", "-p", multiple=True, help="Local paths to sync")
@click.option("--remote-base", default=_REMOTE_BASE, help="Remote base directory")
@click.option("--delete/--no-delete", default=False, help="Delete remote files not in local")
@click.pass_context
def sync_cmd(ctx, paths, remote_base, delete):
    """Sync local project files to the GPU machine."""

    config = ctx.obj["config"]
    backend, inst = get_rental(config, _machine_selector(ctx))
    sync_paths = list(paths) if paths else _SYNC_PATHS

    async def _run():
        await backend.exec(inst, f"mkdir -p {remote_base}", timeout=10)
        for local_path in sync_paths:
            if not os.path.exists(local_path):
                continue
            remote_path = f"{remote_base}/{local_path}"
            await backend.exec(inst, f"mkdir -p {os.path.dirname(remote_path.rstrip('/'))}", timeout=5)
            click.echo(f"  {local_path} -> {inst.user}@{inst.host}:{remote_path}")
            await backend.upload(inst, local_path, remote_path)
        if delete:
            click.echo("Delete requested: remote cleanup must be handled manually.")
        click.echo("Sync complete.")

    run_async(_run())


@click.command(name="run")
@click.argument("command")
@click.option("--sync/--no-sync", "auto_sync", default=True, help="Auto-sync before running")
@click.option("--bg/--fg", "background", default=False, help="Run in background via nohup")
@click.option("--log", default=None, help="Background log file")
@click.option("--cwd", default=_REMOTE_BASE, help="Remote working directory")
@click.pass_context
def run_cmd(ctx, command, auto_sync, background, log, cwd):
    """Sync and run a command on the GPU machine."""

    config = ctx.obj["config"]
    backend, inst = get_rental(config, _machine_selector(ctx))

    async def _run():
        if auto_sync:
            click.echo("Syncing...")
            await backend.exec(inst, f"mkdir -p {cwd}", timeout=10)
            for path in _SYNC_PATHS:
                if os.path.exists(path):
                    await backend.upload(inst, path, f"{cwd}/{path}")

        env = (
            f"cd {cwd} && "
            f"PYTHONPATH={cwd}/scripts:{cwd}/scripts/game "
            "OPENSPIEL_DIR=/root/affinetes/environments/openspiel "
        )
        if background:
            log_path = log or "/root/run.log"
            full_cmd = f"{env}nohup {command} > {log_path} 2>&1 & echo 'PID: $!'"
            _, out, _ = await backend.exec(inst, full_cmd, timeout=15)
        else:
            full_cmd = f"{env}{command}"
            _, out, _ = await backend.exec(inst, full_cmd, timeout=600)
        if out:
            click.echo(out.rstrip())

    run_async(_run())
