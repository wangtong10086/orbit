"""Evaluation and remote dataset commands for remote machines."""

from __future__ import annotations

import asyncio
import os

import click

from orbit.remote_ops.service import get_rental, run_async
from orbit.training.templates import load_template


def _machine_selector(ctx) -> str | None:
    return ctx.parent.params.get("machine")


SGLANG_VENV = "/data/.affine/sglang-venv"
SGLANG_VERSION = "0.4.9.post4"


async def _ensure_sglang_runtime(backend, inst) -> None:
    check_cmd = (
        "bash -lc '"
        "ldconfig -p | grep -q \"libnuma.so.1\" && "
        f"test -f {SGLANG_VENV}/bin/activate && "
        f"source {SGLANG_VENV}/bin/activate && "
        "python3 -c \"import sglang, pybase64; "
        f"assert sglang.__version__ == \\\"{SGLANG_VERSION}\\\"\"'"
    )
    rc, _, _ = await backend.exec(inst, check_cmd, timeout=20)
    if rc == 0:
        return

    install_cmd = (
        "bash -lc 'set -euo pipefail && "
        "apt-get update >/tmp/sglang-apt-update.log 2>&1 && "
        "DEBIAN_FRONTEND=noninteractive apt-get install -y libnuma1 >/tmp/sglang-apt-install.log 2>&1 && "
        "mkdir -p /data/.affine/tools/bin && "
        "if [ ! -x /data/.affine/tools/bin/uv ]; then "
        "curl -LsSf https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-unknown-linux-gnu.tar.gz "
        "| tar xzf - --strip-components=1 -C /data/.affine/tools/bin; "
        "fi && "
        "export PATH=/data/.affine/tools/bin:$PATH && "
        f"uv venv {SGLANG_VENV} --python 3.11 >/tmp/sglang-venv-create.log 2>&1 || true && "
        f"test -f {SGLANG_VENV}/bin/activate && "
        f"source {SGLANG_VENV}/bin/activate && "
        f"uv pip install --upgrade --prerelease=allow \"sglang[all]=={SGLANG_VERSION}\" "
        ">/tmp/sglang-install-all-prerelease.log 2>&1 && "
        "python3 -c \"import sglang, pybase64; "
        f"assert sglang.__version__ == \\\"{SGLANG_VERSION}\\\"\"'"
    )
    rc, _, err = await backend.exec(inst, install_cmd, timeout=1800)
    if rc != 0:
        raise click.ClickException(f"Failed to prepare sglang runtime: {err}")


def _sglang_env_prefix() -> str:
    return (
        "export PATH=/usr/local/cuda/bin:$PATH && "
        "export LD_LIBRARY_PATH=/usr/local/cuda/lib64:/usr/local/cuda-12.8/targets/x86_64-linux/lib:$LD_LIBRARY_PATH && "
        f"source {SGLANG_VENV}/bin/activate && "
        "if [ -f /root/.env ]; then source /root/.env; fi && "
        "export TMPDIR=/root/tmp TRITON_CACHE_DIR=/root/.triton_cache && "
    )


@click.command(name="start-sglang")
@click.argument("model")
@click.option("--port", default=30000, type=int)
@click.option("--tp", default=4, type=int)
@click.option("--dp", default=1, type=int, help="Data parallelism")
@click.option("--mem-frac", default=0.80, type=float, help="GPU memory fraction for KV cache")
@click.option("--wait/--no-wait", default=True, help="Wait for server to be ready")
@click.pass_context
def start_sglang(ctx, model, port, tp, dp, mem_frac, wait):
    """Start sglang inference server on a rental machine."""

    import time as time_mod

    config = ctx.obj["config"]
    backend, inst = get_rental(config, _machine_selector(ctx))

    async def _run():
        await _ensure_sglang_runtime(backend, inst)
        await backend.exec(inst, "mkdir -p /root/logs /root/tmp /root/.triton_cache", timeout=15)
        await backend.exec(inst, "pkill -9 -f sglang 2>/dev/null; screen -S sglang -X quit 2>/dev/null; sleep 2", timeout=15)

        dp_flag = f"--dp {dp} " if dp > 1 else ""
        cmd = (
            "screen -dmS sglang bash -c '"
            f"{_sglang_env_prefix()}"
            f"python3 -m sglang.launch_server --model-path {model} --port {port} --host 0.0.0.0 --tp {tp} "
            f"{dp_flag}"
            "--trust-remote-code --disable-cuda-graph --disable-radix-cache "
            "--tool-call-parser qwen25 "
            f"--mem-fraction-static {mem_frac} "
            "2>&1 | tee /root/logs/sglang.log'"
        )
        click.echo(f"Starting sglang with {model} (tp={tp}, dp={dp}, mem={mem_frac})...")
        rc, _, err = await backend.exec(inst, cmd, timeout=15)
        if rc != 0:
            raise click.ClickException(f"Failed: {err}")

        if not wait:
            click.echo(f"sglang started on port {port}.")
            return

        click.echo("Waiting for sglang to be ready...")
        for index in range(24):
            time_mod.sleep(15)
            rc, out, _ = await backend.exec(inst, f"curl -s -m 5 http://127.0.0.1:{port}/v1/models 2>/dev/null", timeout=10)
            if rc == 0 and out and "model" in out:
                click.echo(f"sglang ready after {(index + 1) * 15}s")
                try:
                    rc, out, _ = await backend.exec(
                        inst, f"curl -s -m 5 http://172.17.0.1:{port}/v1/models 2>/dev/null", timeout=10
                    )
                    if rc == 0 and out and "model" in out:
                        click.echo("Docker bridge (172.17.0.1) connectivity: OK")
                    else:
                        click.echo("WARNING: Docker bridge (172.17.0.1) not reachable")
                except Exception:
                    click.echo("WARNING: Docker bridge (172.17.0.1) probe timed out")
                return
            rc, _, _ = await backend.exec(inst, "screen -ls | grep -q sglang", timeout=5)
            if rc != 0:
                _, log, _ = await backend.exec(inst, "tail -5 /root/logs/sglang.log 2>/dev/null", timeout=5)
                raise click.ClickException(f"sglang crashed during startup:\n{log}")
        raise click.ClickException("sglang did not become ready within 6 minutes")

    run_async(_run())


@click.command(name="start-eval")
@click.argument("model")
@click.option("--envs", default="GAME,NAVWORLD,SWE-INFINITE,LIVEWEB", help="Comma-separated envs")
@click.option("--samples", default=100, type=int)
@click.option("--base-url", default="http://172.17.0.1:30000/v1")
@click.pass_context
def start_eval(ctx, model, envs, samples, base_url):
    """Start multi-env evaluation on rental."""

    config = ctx.obj["config"]
    backend, inst = get_rental(config, _machine_selector(ctx))

    async def _run():
        env_list = envs.replace(",", " ")
        cmd = (
            "screen -dmS eval bash -c '"
            "source /data/.affine/activate.sh && "
            "[ ! -f /root/.env ] || source /root/.env && "
            "cd /root/affinetes && "
            "python3 /root/scripts/eval_envs.py "
            f"--base-url {base_url} --model {model} --envs {env_list} --samples {samples} "
            "--output-dir /root/logs --affinetes-dir /root/affinetes --skip-build "
            "2>&1 | tee /root/logs/eval.log'"
        )
        click.echo(f"Starting eval: {envs} x {samples} samples")
        rc, _, err = await backend.exec(inst, cmd, timeout=15)
        if rc != 0:
            raise click.ClickException(f"Failed: {err}")
        click.echo("Eval started. Monitor: orbit remote machine exec 'tail -5 /root/logs/eval.log'")

    run_async(_run())


@click.command(name="prepare-data")
@click.option("--data-dir", default="data/canonical", help="Local data directory")
@click.option("--envs", default="GAME,NAVWORLD,SWE-INFINITE,LIVEWEB", help="Environments to include")
@click.option("--remote-path", default="/root/data/combined.jsonl", help="Remote destination path")
@click.pass_context
def prepare_data(ctx, data_dir, envs, remote_path):
    """Combine local env data files, normalize schema, and upload to rental."""

    import json
    import tempfile

    from orbit.foundation.packing import Qwen3ConversationPacker

    config = ctx.obj["config"]
    backend, inst = get_rental(config, _machine_selector(ctx))
    env_files = {
        "GAME": "game.jsonl",
        "NAVWORLD": "navworld.jsonl",
        "SWE-INFINITE": "swe_infinite.jsonl",
        "LIVEWEB": "liveweb.jsonl",
        "LGC-v2": "lgc_v2.jsonl",
        "PRINT": "print.jsonl",
    }
    data_path = config.project_root / data_dir
    env_list = [env.strip() for env in envs.split(",")]
    packer = Qwen3ConversationPacker()
    lines: list[str] = []
    total = 0

    for env_name in env_list:
        filename = env_files.get(env_name)
        if not filename:
            raise click.ClickException(f"Unknown env: {env_name}")
        path = data_path / filename
        if not path.exists():
            raise click.ClickException(f"File not found: {path}")
        count = 0
        with open(path) as handle:
            for line in handle:
                record = json.loads(line)
                normalized = packer.pack(record)
                lines.append(json.dumps({"messages": normalized}, ensure_ascii=False))
                count += 1
        click.echo(f"  {env_name}: {count} samples")
        total += count

    click.echo(f"  Total: {total} samples")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as handle:
        handle.write("\n".join(lines) + "\n")
        tmp_path = handle.name

    async def _run():
        click.echo(f"Uploading to {remote_path}...")
        await backend.upload(inst, tmp_path, remote_path)
        os.unlink(tmp_path)
        rc, out, _ = await backend.exec(inst, f"wc -l {remote_path}", timeout=10)
        if rc == 0:
            click.echo(f"Done: {out.strip()}")

    run_async(_run())


@click.command(name="eval-pipeline")
@click.option("--model", default="/root/merged_model", help="Model path on remote")
@click.option("--checkpoint", default=None, help="LoRA checkpoint to merge")
@click.option("--envs", default="GAME,NAVWORLD,SWE-INFINITE,LIVEWEB", help="Comma-separated envs")
@click.option("--samples", default=100, type=int)
@click.option("--tp", default=4, type=int)
@click.option("--port", default=30000, type=int)
@click.pass_context
def eval_pipeline(ctx, model, checkpoint, envs, samples, tp, port):
    """One-command eval pipeline on the rental machine."""

    config = ctx.obj["config"]
    backend, inst = get_rental(config, _machine_selector(ctx))

    async def _run():
        await _ensure_sglang_runtime(backend, inst)
        base_url = f"http://172.17.0.1:{port}/v1"
        click.echo("Step 1/5: Cleaning up old processes...")
        await backend.exec(
            inst,
            "pkill -9 -f sglang 2>/dev/null; pkill -9 -f eval_envs 2>/dev/null; "
            "screen -S sglang -X quit 2>/dev/null; screen -S eval -X quit 2>/dev/null; sleep 2",
            timeout=15,
        )

        click.echo("Step 2/5: Ensuring CUDA env...")
        await backend.exec(
            inst,
            "test -f /usr/local/cuda/lib64/libcudart.so || "
            "ln -sf /usr/local/cuda-12.8/targets/x86_64-linux/lib/libcudart.so /usr/local/cuda/lib64/libcudart.so",
            timeout=10,
        )

        if checkpoint:
            click.echo(f"Step 3/5: Merging LoRA from {checkpoint}...")
            rc, out, err = await backend.exec(
                inst,
                f"{_sglang_env_prefix()} python3 /root/scripts/merge_lora.py {checkpoint} {model}",
                timeout=600,
            )
            if rc != 0:
                raise click.ClickException(f"LoRA merge failed: {err}")
            click.echo(f"  Merged: {out.strip().split(chr(10))[-1]}")
        else:
            click.echo("Step 3/5: Skipping merge (using existing merged model)")

        click.echo(f"Step 4/5: Deploying sglang (tp={tp})...")
        cmd = (
            "screen -dmS sglang bash -c '"
            f"{_sglang_env_prefix()}"
            f"python3 -m sglang.launch_server --model-path {model} --port {port} --host 0.0.0.0 --tp {tp} "
            "--trust-remote-code --disable-cuda-graph --disable-radix-cache "
            "--tool-call-parser qwen25 "
            "--mem-fraction-static 0.88 "
            "2>&1 | tee /root/logs/sglang.log'"
        )
        rc, _, err = await backend.exec(inst, cmd, timeout=15)
        if rc != 0:
            raise click.ClickException(f"sglang launch failed: {err}")

        click.echo("  Waiting for sglang to be ready", nl=False)
        for _ in range(60):
            await asyncio.sleep(5)
            rc, out, _ = await backend.exec(
                inst,
                f"curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:{port}/health 2>/dev/null || echo 000",
                timeout=10,
            )
            if out.strip().replace("'", "") == "200":
                click.echo(" READY!")
                break
            _, log_tail, _ = await backend.exec(inst, "tail -2 /root/logs/sglang.log 2>/dev/null", timeout=5)
            if "SIGQUIT" in (log_tail or "") or "exception" in (log_tail or "").lower():
                click.echo(" FAILED!")
                raise click.ClickException("sglang crashed. Check remote logs.")
            click.echo(".", nl=False)
        else:
            click.echo(" TIMEOUT!")
            raise click.ClickException("sglang failed to start within 5 minutes")

        click.echo(f"Step 5/5: Starting eval ({envs} x {samples} samples)...")
        env_list = envs.replace(",", " ")
        eval_cmd = (
            "screen -dmS eval bash -c '"
            "source /data/.affine/activate.sh && "
            "[ ! -f /root/.env ] || source /root/.env && "
            "cd /root/affinetes && "
            "python3 /root/scripts/eval_envs.py "
            f"--base-url {base_url} --model {model} --envs {env_list} --samples {samples} "
            "--output-dir /root/logs --affinetes-dir /root/affinetes --skip-build "
            "2>&1 | tee /root/logs/eval.log'"
        )
        rc, _, err = await backend.exec(inst, eval_cmd, timeout=15)
        if rc != 0:
            raise click.ClickException(f"Eval launch failed: {err}")

        click.echo("\nEval pipeline running! Monitor with:")
        click.echo("  orbit remote machine exec 'tail -20 /root/logs/eval.log'")

    run_async(_run())


@click.command(name="clean-data")
@click.argument("dataset_path")
@click.option("--remove-envs", default="LGC-v2,PRINT", help="Envs to remove")
@click.option("-o", "--output", default=None, help="Output path (default: overwrite input)")
@click.pass_context
def clean_data(ctx, dataset_path, remove_envs, output):
    """Remove unwanted environment data from a remote dataset."""

    config = ctx.obj["config"]
    backend, inst = get_rental(config, _machine_selector(ctx))
    out_path = output or dataset_path

    async def _run():
        remove_set = remove_envs.split(",")
        remove_patterns = {
            "LGC-v2": "Dyck|operator|bool|crypto|sudoku|数字.*目标",
            "PRINT": "Predict the exact.*output|predict.*stdout",
        }
        conditions = [remove_patterns[env] for env in remove_set if env in remove_patterns]
        pattern = "|".join(conditions)

        script = f"""python3 -c "
import json, re
pattern = re.compile(r'{pattern}', re.IGNORECASE)
kept, removed = 0, 0
lines = open('{dataset_path}').readlines()
with open('{out_path}', 'w') as handle:
    for line in lines:
        record = json.loads(line)
        msgs = record.get('messages', [])
        text = ''
        if msgs:
            text = msgs[0].get('content', '')
            if len(msgs) > 1:
                text += ' ' + msgs[1].get('content', '')[:200]
        if msgs and not msgs[0].get('content', '').strip() and pattern.search(text):
            removed += 1
            continue
        if msgs and pattern.search(msgs[0].get('content', '')[:300]):
            removed += 1
            continue
        kept += 1
        handle.write(line)
print(f'Kept: {{kept}}, Removed: {{removed}}')
" """

        click.echo(f"Cleaning {dataset_path}: removing {remove_envs}...")
        rc, out, err = await backend.exec(inst, script, timeout=30)
        if rc != 0:
            raise click.ClickException(f"Failed: {err}")
        click.echo(out.strip())

    run_async(_run())
