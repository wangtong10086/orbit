"""CLI rental machine subcommands for Affine Forge."""

import asyncio
import os
import click


def run_async(coro):
    """Helper to run async functions from Click commands."""
    return asyncio.run(coro)


@click.group()
@click.pass_context
def rental(ctx):
    """Remote rental machine management (SSH backend)."""
    pass


def _get_rental(config) -> tuple:
    """Load the first machine from machines.json, return (SshBackend, GpuInstance)."""
    from forge.compute.ssh import SshBackend
    from forge.compute.base import GpuInstance
    import json as json_mod

    machines_path = config.project_root / "machines.json"
    if not machines_path.exists():
        raise click.ClickException("machines.json not found. Register a machine first.")

    with open(machines_path) as f:
        data = json_mod.load(f)

    machines = data.get("machines", [])
    if not machines:
        raise click.ClickException("No machines in machines.json")

    m = machines[0]
    backend = SshBackend(str(machines_path))
    instance = GpuInstance(
        id=m.get("name", m["host"]),
        backend="ssh",
        gpu_type=m.get("gpu_type", "unknown"),
        status="unknown",
        host=m["host"],
        port=m.get("port", 22),
        user=m.get("user", "root"),
        metadata=m,
    )
    return backend, instance


@rental.command()
@click.pass_context
def status(ctx):
    """Show rental GPU, processes, and training status."""
    config = ctx.obj["config"]
    backend, inst = _get_rental(config)

    async def _run():
        health = await backend.health_check(inst)
        click.echo(f"\n=== {inst.id} ({inst.host}) ===")
        click.echo(f"Status: {health.get('status', '?')}")

        if health.get("gpu_info"):
            click.echo(f"\nGPU:")
            for line in health["gpu_info"]:
                click.echo(f"  {line.strip()}")

        click.echo(f"Disk free: {health.get('disk_free', '?')}")
        click.echo(f"Training: {health.get('training', '?')}")
        click.echo(f"Checkpoint: {health.get('latest_checkpoint', 'none')}")

        # Extra: screen sessions and sglang
        rc, out, _ = await backend.exec(inst, "screen -ls 2>/dev/null || true", timeout=10)
        if rc == 0 and out.strip():
            click.echo(f"\nScreens:\n{out.strip()}")

    run_async(_run())


@rental.command(name="exec")
@click.argument("command")
@click.option("--timeout", default=60, type=int, help="Timeout in seconds")
@click.pass_context
def rental_exec(ctx, command, timeout):
    """Execute a command on the rental machine."""
    config = ctx.obj["config"]
    backend, inst = _get_rental(config)

    async def _run():
        rc, stdout, stderr = await backend.exec(inst, command, timeout=timeout)
        if stdout:
            click.echo(stdout.rstrip())
        if stderr:
            click.echo(stderr.rstrip(), err=True)
        if rc != 0:
            raise SystemExit(rc)

    run_async(_run())


@rental.command()
@click.argument("process", type=click.Choice(["sglang", "eval", "training", "all"]))
@click.pass_context
def kill(ctx, process):
    """Kill a process on the rental (sglang, eval, training, all)."""
    config = ctx.obj["config"]
    backend, inst = _get_rental(config)

    kill_cmds = {
        "sglang": "pkill -9 -f sglang; screen -S sglang -X quit 2>/dev/null",
        "eval": "pkill -9 -f eval_envs; screen -S eval -X quit 2>/dev/null",
        "training": "pkill -9 -f train; screen -S train -X quit 2>/dev/null",
        "all": "pkill -9 -f sglang; pkill -9 -f eval_envs; pkill -9 -f train; screen -wipe 2>/dev/null",
    }

    async def _run():
        cmd = kill_cmds[process]
        click.echo(f"Killing {process}...")
        await backend.exec(inst, cmd, timeout=15)
        # Verify
        rc, out, _ = await backend.exec(inst,
            "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader",
            timeout=15)
        if rc == 0:
            click.echo(f"\nGPU after kill:")
            for line in out.strip().split("\n"):
                click.echo(f"  {line.strip()}")

    run_async(_run())


@rental.command(name="start-training")
@click.argument("script_path")
@click.option("--tp", default=4, type=int, help="Tensor parallel degree")
@click.pass_context
def start_training(ctx, script_path, tp):
    """Start training on rental in a detached screen session."""
    config = ctx.obj["config"]
    backend, inst = _get_rental(config)

    async def _run():
        # Upload script
        remote_script = f"/root/scripts/{os.path.basename(script_path)}"
        click.echo(f"Uploading {script_path} → {remote_script}")
        await backend.upload(inst, script_path, remote_script)

        # Start in screen
        train_cmd = (
            f"screen -dmS train bash -c '"
            f"source /root/venv/bin/activate && "
            f"source /root/.env && "
            f"cd /root && "
            f"python3 {remote_script} 2>&1 | tee /root/logs/train.log"
            f"'"
        )
        click.echo("Starting training in screen 'train'...")
        rc, out, err = await backend.exec(inst, train_cmd, timeout=15)
        if rc != 0:
            raise click.ClickException(f"Failed to start: {err}")

        click.echo("Training started. Monitor with: forge rental status")

    run_async(_run())


@rental.command(name="start-sglang")
@click.argument("model")
@click.option("--port", default=30000, type=int)
@click.option("--tp", default=4, type=int)
@click.pass_context
def start_sglang(ctx, model, port, tp):
    """Start sglang inference server on rental."""
    config = ctx.obj["config"]
    backend, inst = _get_rental(config)

    async def _run():
        cmd = (
            f"screen -dmS sglang bash -c '"
            f"source /root/venv/bin/activate && "
            f"source /root/.env && "
            f"export TMPDIR=/root/tmp TRITON_CACHE_DIR=/root/.triton_cache && "
            f"python3 -m sglang.launch_server "
            f"--model-path {model} --port {port} --host 0.0.0.0 --tp {tp} "
            f"--trust-remote-code --disable-cuda-graph --disable-radix-cache "
            f"--tool-call-parser qwen25 "
            f"--mem-fraction-static 0.88 "
            f"2>&1 | tee /root/logs/sglang.log"
            f"'"
        )
        click.echo(f"Starting sglang with {model} (tp={tp})...")
        rc, _, err = await backend.exec(inst, cmd, timeout=15)
        if rc != 0:
            raise click.ClickException(f"Failed: {err}")
        click.echo(f"sglang started on port {port}. Check: forge rental exec 'curl -s http://127.0.0.1:{port}/health'")

    run_async(_run())


@rental.command(name="start-eval")
@click.argument("model")
@click.option("--envs", default="GAME,NAVWORLD,SWE-SYNTH,LIVEWEB", help="Comma-separated envs")
@click.option("--samples", default=100, type=int)
@click.option("--base-url", default="http://127.0.0.1:30000/v1")
@click.pass_context
def start_eval(ctx, model, envs, samples, base_url):
    """Start multi-env evaluation on rental."""
    config = ctx.obj["config"]
    backend, inst = _get_rental(config)

    async def _run():
        env_list = envs.replace(",", " ")
        cmd = (
            f"screen -dmS eval bash -c '"
            f"source /root/venv/bin/activate && "
            f"source /root/.env && "
            f"cd /root/affinetes && "
            f"python3 /root/scripts/eval_envs.py "
            f"--base-url {base_url} --model {model} "
            f"--envs {env_list} --samples {samples} "
            f"--output-dir /root/logs --affinetes-dir /root/affinetes --skip-build "
            f"2>&1 | tee /root/logs/eval.log"
            f"'"
        )
        click.echo(f"Starting eval: {envs} × {samples} samples")
        rc, _, err = await backend.exec(inst, cmd, timeout=15)
        if rc != 0:
            raise click.ClickException(f"Failed: {err}")
        click.echo("Eval started. Monitor: forge rental exec 'tail -5 /root/logs/eval.log'")

    run_async(_run())


@rental.command(name="clean-data")
@click.argument("dataset_path")
@click.option("--remove-envs", default="LGC-v2,PRINT", help="Envs to remove (comma-separated)")
@click.option("-o", "--output", default=None, help="Output path (default: overwrite input)")
@click.pass_context
def clean_data(ctx, dataset_path, remove_envs, output):
    """Remove unwanted environment data from a dataset on rental."""
    config = ctx.obj["config"]
    backend, inst = _get_rental(config)
    out_path = output or dataset_path

    async def _run():
        # Build filter script inline
        remove_set = remove_envs.split(",")
        remove_patterns = {
            "LGC-v2": "Dyck|operator|bool|crypto|sudoku|数字.*目标",
            "PRINT": "Predict the exact.*output|predict.*stdout",
        }
        conditions = []
        for env in remove_set:
            if env in remove_patterns:
                conditions.append(remove_patterns[env])

        pattern = "|".join(conditions)

        script = f'''python3 -c "
import json, re, sys
pattern = re.compile(r'{pattern}', re.IGNORECASE)
kept, removed = 0, 0
lines = open('{dataset_path}').readlines()
with open('{out_path}', 'w') as f:
    for line in lines:
        d = json.loads(line)
        msgs = d.get('messages', [])
        text = ''
        if msgs:
            text = msgs[0].get('content', '')
            if len(msgs) > 1:
                text += ' ' + msgs[1].get('content', '')[:200]
        if not msgs[0].get('content', '').strip() and pattern.search(text):
            removed += 1
            continue
        if pattern.search(msgs[0].get('content', '')[:300]):
            removed += 1
            continue
        kept += 1
        f.write(line)
print(f'Kept: {{kept}}, Removed: {{removed}}')
"'''

        click.echo(f"Cleaning {dataset_path}: removing {remove_envs}...")
        rc, out, err = await backend.exec(inst, script, timeout=30)
        if rc == 0:
            click.echo(out.strip())
        else:
            raise click.ClickException(f"Failed: {err}")

    run_async(_run())
