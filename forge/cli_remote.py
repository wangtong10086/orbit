"""CLI remote machine operations — works with any SSH-reachable machine.

Usage: forge remote -m <machine> <command>

Machine names are defined in machines.json. Supports Targon rentals,
AWS/GCP instances, or any host with SSH access.
"""

import asyncio
import os
import click


def run_async(coro):
    """Helper to run async functions from Click commands."""
    return asyncio.run(coro)


def resolve_machine(config, machine_selector=None) -> tuple:
    """Resolve a machine from machines.json → (SshBackend, GpuInstance).

    Args:
        machine_selector: Machine name (e.g. "m1") or 0-based index. None = first.

    Returns:
        Tuple of (SshBackend, GpuInstance) ready for remote operations.
    """
    from forge.compute.ssh import SshBackend
    from forge.compute.base import GpuInstance
    import json as json_mod

    machines_path = config.project_root / "machines.json"
    if not machines_path.exists():
        raise click.ClickException("machines.json not found")

    with open(machines_path) as f:
        machines = json_mod.load(f).get("machines", [])

    if not machines:
        raise click.ClickException("No machines in machines.json")

    if machine_selector is None:
        m = machines[0]
    elif machine_selector.isdigit():
        idx = int(machine_selector)
        if idx >= len(machines):
            raise click.ClickException(f"Machine index {idx} out of range (have {len(machines)})")
        m = machines[idx]
    else:
        m = next((x for x in machines if x.get("name") == machine_selector), None)
        if m is None:
            names = [x.get("name", x["user"]) for x in machines]
            raise click.ClickException(f"Machine '{machine_selector}' not found. Available: {names}")

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


def _get_machine(ctx):
    """Shorthand: resolve machine from Click context."""
    config = ctx.obj["config"]
    selector = ctx.parent.params.get("machine")
    return resolve_machine(config, selector)


# ---------------------------------------------------------------------------
# Click group
# ---------------------------------------------------------------------------

@click.group()
@click.option("--machine", "-m", default=None, help="Machine name or index from machines.json")
@click.pass_context
def remote(ctx, machine):
    """Remote machine operations (any SSH-reachable host)."""
    ctx.ensure_object(dict)
    ctx.obj["machine_selector"] = machine


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------

@remote.command(name="exec")
@click.argument("command")
@click.option("--timeout", "-t", default=60, type=int, help="Timeout seconds")
@click.pass_context
def remote_exec(ctx, command, timeout):
    """Execute a command on remote machine.

    \b
    forge remote -m m1 exec "nvidia-smi"
    forge remote -m m1 exec "screen -ls" -t 10
    """
    backend, inst = _get_machine(ctx)

    async def _run():
        rc, stdout, stderr = await backend.exec(inst, command, timeout=timeout)
        if stdout:
            click.echo(stdout.rstrip())
        if stderr:
            click.echo(stderr.rstrip(), err=True)
        if rc != 0:
            raise SystemExit(rc)

    run_async(_run())


@remote.command()
@click.pass_context
def status(ctx):
    """Show GPU, processes, disk, and screen sessions.

    \b
    forge remote -m m1 status
    """
    backend, inst = _get_machine(ctx)

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

        rc, out, _ = await backend.exec(inst, "screen -ls 2>/dev/null || true", timeout=10)
        if rc == 0 and out.strip():
            click.echo(f"\nScreens:\n{out.strip()}")

    run_async(_run())


@remote.command()
@click.argument("process", type=click.Choice(["sglang", "eval", "training", "all"]))
@click.pass_context
def kill(ctx, process):
    """Kill processes on remote machine.

    \b
    forge remote -m m1 kill sglang
    forge remote -m m1 kill all
    """
    backend, inst = _get_machine(ctx)

    kill_cmds = {
        "sglang": "pkill -9 -f sglang; screen -S sglang -X quit 2>/dev/null",
        "eval": "pkill -9 -f eval_envs; screen -S eval -X quit 2>/dev/null",
        "training": "pkill -9 -f train; screen -S train -X quit 2>/dev/null",
        "all": "pkill -9 -f sglang; pkill -9 -f eval_envs; pkill -9 -f train; screen -wipe 2>/dev/null",
    }

    async def _run():
        click.echo(f"Killing {process}...")
        await backend.exec(inst, kill_cmds[process], timeout=15)
        rc, out, _ = await backend.exec(inst,
            "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader",
            timeout=15)
        if rc == 0:
            click.echo(f"GPU after kill:")
            for line in out.strip().split("\n"):
                click.echo(f"  {line.strip()}")

    run_async(_run())


# ---------------------------------------------------------------------------
# File transfer
# ---------------------------------------------------------------------------

@remote.command()
@click.argument("local_path")
@click.argument("remote_path")
@click.pass_context
def upload(ctx, local_path, remote_path):
    """Upload file/dir to remote machine (rsync, scp fallback).

    \b
    forge remote -m m1 upload data/combined.jsonl /root/data/combined.jsonl
    forge remote -m m1 upload scripts/ /root/scripts/
    """
    backend, inst = _get_machine(ctx)

    async def _run():
        click.echo(f"{local_path} → {inst.id}:{remote_path}")
        await backend.upload(inst, local_path, remote_path)
        click.echo("Done.")

    run_async(_run())


@remote.command()
@click.argument("remote_path")
@click.argument("local_path")
@click.pass_context
def download(ctx, remote_path, local_path):
    """Download file/dir from remote machine.

    \b
    forge remote -m m1 download /root/logs/train.log ./train.log
    """
    backend, inst = _get_machine(ctx)

    async def _run():
        click.echo(f"{inst.id}:{remote_path} → {local_path}")
        await backend.download(inst, remote_path, local_path)
        click.echo("Done.")

    run_async(_run())


@remote.command()
@click.argument("source_machine")
@click.argument("remote_path")
@click.option("--dest-path", default=None, help="Destination path (default: same as source)")
@click.pass_context
def transfer(ctx, source_machine, remote_path, dest_path):
    """Transfer file between two machines via local relay.

    \b
    forge remote -m m1 transfer m2 /root/merged_model
    """
    import tempfile
    config = ctx.obj["config"]
    backend, src_inst = resolve_machine(config, source_machine)
    _, dst_inst = _get_machine(ctx)
    dst = dest_path or remote_path

    async def _run():
        with tempfile.TemporaryDirectory() as tmp:
            click.echo(f"{src_inst.id}:{remote_path} → {dst_inst.id}:{dst}")
            await backend.download(src_inst, remote_path, f"{tmp}/")
            await backend.upload(dst_inst, f"{tmp}/", os.path.dirname(dst) + "/")
            click.echo("Done.")

    run_async(_run())


# ---------------------------------------------------------------------------
# Sync & Run
# ---------------------------------------------------------------------------

_SYNC_PATHS = ["scripts/", "forge/", "knowledge/", "experiments/"]
_REMOTE_BASE = "/root/project"


@remote.command()
@click.option("--paths", "-p", multiple=True, help="Local paths to sync (default: scripts/ forge/)")
@click.option("--remote-base", default=_REMOTE_BASE)
@click.option("--delete/--no-delete", default=False, help="Delete remote files not in local")
@click.pass_context
def sync(ctx, paths, remote_base, delete):
    """Sync local project files to remote machine.

    \b
    forge remote -m m1 sync
    forge remote -m m1 sync -p scripts/ -p forge/
    """
    backend, inst = _get_machine(ctx)
    sync_paths = list(paths) if paths else _SYNC_PATHS

    async def _run():
        await backend.exec(inst, f"mkdir -p {remote_base}", timeout=10)
        for local_path in sync_paths:
            if not os.path.exists(local_path):
                continue
            remote_path = f"{remote_base}/{local_path}"
            click.echo(f"  {local_path} → {inst.id}:{remote_path}")
            await backend.upload(inst, local_path, remote_path)
        click.echo("Sync complete.")

    run_async(_run())


@remote.command()
@click.argument("command")
@click.option("--sync/--no-sync", "auto_sync", default=True, help="Auto-sync before running")
@click.option("--bg/--fg", "background", default=False, help="Run in background")
@click.option("--log", default=None, help="Background log file")
@click.option("--cwd", default=_REMOTE_BASE, help="Remote working directory")
@click.pass_context
def run(ctx, command, auto_sync, background, log, cwd):
    """Sync project + run command on remote.

    \b
    forge remote -m m1 run "python3 scripts/test.py"
    forge remote -m m1 run --bg "python3 scripts/train.py"
    """
    backend, inst = _get_machine(ctx)

    async def _run():
        if auto_sync:
            click.echo("Syncing...")
            await backend.exec(inst, f"mkdir -p {cwd}", timeout=10)
            for p in _SYNC_PATHS:
                if os.path.exists(p):
                    await backend.upload(inst, p, f"{cwd}/{p}")

        env = f"cd {cwd} && PYTHONPATH={cwd}/scripts:{cwd}/scripts/game OPENSPIEL_DIR=/root/affinetes/environments/openspiel"
        if background:
            log_path = log or "/root/run.log"
            full_cmd = f"{env} nohup {command} > {log_path} 2>&1 & echo 'PID: $!'"
        else:
            full_cmd = f"{env} {command}"
        rc, out, err = await backend.exec(inst, full_cmd, timeout=600)
        if out:
            click.echo(out.rstrip())

    run_async(_run())


# ---------------------------------------------------------------------------
# Machine setup
# ---------------------------------------------------------------------------

@remote.command()
@click.pass_context
def setup(ctx):
    """Full machine setup: system, venv, ms-swift, model, data — one command.

    Uses /data persistent volume (survives container rebuilds) for:
    - /data/venv      → Python venv + all packages
    - /data/models    → Model weights
    - /data/datasets  → Training data
    - /data/checkpoints → Training checkpoints
    - /data/logs      → Training logs
    - /data/.env      → Environment variables

    Symlinks from /root point to /data. On rebuild, only system
    packages need reinstall — everything else is already on /data.

    \b
    forge remote -m m3 setup
    """
    from pathlib import Path

    backend, inst = _get_machine(ctx)
    machine_name = ctx.parent.params.get("machine", "?")

    # Read local .env for tokens
    env_path = Path(__file__).parent.parent / ".env"
    env_vars = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip()

    hf_token = env_vars.get("HF_TOKEN", "")
    amap_key = env_vars.get("AMAP_API_KEY", "")
    amap_maps_key = env_vars.get("AMAP_MAPS_API_KEY", "")

    model = "Qwen/Qwen3-32B"
    data_repo = "monokoco/affine-sft-data"
    data_files = ["game.jsonl", "navworld.jsonl", "liveweb.jsonl", "swe_infinite.jsonl", "memorygym.jsonl"]

    async def _run():
        async def step(name, cmd, timeout=600):
            click.echo(f"\n=== [{name}] ===")
            rc, out, err = await backend.exec(inst, cmd, timeout=timeout)
            if out:
                for line in out.strip().split("\n")[-5:]:
                    click.echo(f"  {line}")
            if rc != 0:
                click.echo(f"  FAILED (rc={rc})")
                if err:
                    click.echo(f"  {err[:200]}")
                return False
            return True

        # 0. Check /data mount
        if not await step("0. Check /data persistent volume",
            "bash -c 'test -d /data && echo \"/data mounted ($(df -h /data | tail -1 | awk \"{print \\$2}\") total)\" || echo \"NO /data MOUNT\"'",
            timeout=10):
            click.echo("WARNING: /data not mounted, using /root (data will be lost on rebuild)")

        # 1. System packages (always needed after rebuild)
        if not await step("1. System packages",
            "bash -c '"
            "export DEBIAN_FRONTEND=noninteractive && "
            "rm -f /etc/apt/sources.list.d/cuda*.list 2>/dev/null; "
            "apt-get update -qq 2>&1 | tail -1 && "
            "apt-get install -y -qq python3 python3-venv python3-pip git screen curl wget "
            "build-essential libnuma1 libnuma-dev gpg > /dev/null 2>&1 && "
            "python3 --version'"):
            click.echo("FATAL: System packages failed. Aborting.")
            return

        # 2. CUDA toolkit (required for deepspeed JIT)
        if not await step("2. CUDA toolkit",
            "bash -c '"
            'if [ -f /usr/local/cuda/bin/nvcc ]; then echo "CUDA already installed"; /usr/local/cuda/bin/nvcc --version | tail -1; exit 0; fi; '
            "export DEBIAN_FRONTEND=noninteractive && "
            "curl -fsSL https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/3bf863cc.pub "
            "| gpg --dearmor -o /usr/share/keyrings/cuda-archive-keyring.gpg 2>/dev/null && "
            'echo \"deb [signed-by=/usr/share/keyrings/cuda-archive-keyring.gpg] '
            'https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/ /\" '
            "> /etc/apt/sources.list.d/cuda.list && "
            "apt-get update -qq 2>&1 | tail -1 && "
            "apt-get install -y --no-install-recommends cuda-nvcc-12-8 cuda-cudart-dev-12-8 2>&1 | tail -3 && "
            "ln -sf /usr/local/cuda-12.8 /usr/local/cuda && "
            "/usr/local/cuda/bin/nvcc --version | tail -1'",
            timeout=120):
            click.echo("FATAL: CUDA toolkit install failed. Aborting.")
            return

        # 3. Persistent directories on /data
        await step("3. Create /data directories + symlinks",
            "bash -c '"
            "mkdir -p /data/{venv,models,datasets,checkpoints,logs,scripts,configs} && "
            "rm -rf /root/venv /root/models /root/data /root/checkpoints /root/logs 2>/dev/null; "
            "ln -sf /data/venv /root/venv && "
            "ln -sf /data/models /root/models && "
            "ln -sf /data/datasets /root/data && "
            "ln -sf /data/checkpoints /root/checkpoints && "
            "ln -sf /data/logs /root/logs && "
            "ln -sf /data/scripts /root/scripts && "
            "echo symlinks_created'")

        # 3. Venv (skip if already exists on /data)
        if not await step("3. Venv (persistent on /data/venv)",
            "bash -c '"
            'if [ -f /data/venv/bin/activate ]; then echo "Venv exists on /data, reusing"; '
            ". /data/venv/bin/activate && python3 --version; exit 0; fi; "
            "python3 -m venv /data/venv && "
            ". /data/venv/bin/activate && pip install -q --upgrade pip && "
            "echo venv_created'"):
            click.echo("FATAL: Venv failed. Aborting.")
            return

        # 4. ML stack (skip if torch already works)
        if not await step("4. ML stack (torch + ms-swift + deepspeed + sglang)",
            "bash -c '. /data/venv/bin/activate && "
            "python3 -c \"import torch; print(f\\\"torch={torch.__version__} cuda={torch.cuda.is_available()}\\\")\" 2>/dev/null && "
            "python3 -c \"import swift\" 2>/dev/null && "
            "echo \"ML stack already installed\" || ("
            "pip install -q torch torchvision torchaudio && "
            "pip install -q \"ms-swift[llm]>=4.0\" deepspeed accelerate huggingface_hub && "
            "pip install -q \"sglang[all]\" nest_asyncio docker openai httpx && "
            "python3 -c \"import torch; print(f\\\"torch={torch.__version__} cuda={torch.cuda.is_available()}\\\")\")'",
            timeout=600):
            click.echo("FATAL: ML stack failed. Aborting.")
            return

        # 5. Flash-attn (optional, skip if exists)
        await step("5. flash-attn (optional)",
            "bash -c '. /data/venv/bin/activate && "
            "python3 -c \"import flash_attn; print(f\\\"flash_attn={flash_attn.__version__}\\\")\" 2>/dev/null && "
            "echo \"flash-attn already installed\" || "
            "(pip install -q flash-attn --no-build-isolation 2>&1 | tail -1 || "
            "echo \"flash-attn skipped (will use sdpa)\")'",
            timeout=600)

        # 6. .env + HF login
        env_lines = f"export HF_TOKEN={hf_token}\\nexport AMAP_API_KEY={amap_key}\\nexport AMAP_MAPS_API_KEY={amap_maps_key}"
        if not await step("6. .env + HF login",
            f"bash -c 'printf \"{env_lines}\\n\" > /data/.env && ln -sf /data/.env /root/.env && "
            + (f". /data/venv/bin/activate && huggingface-cli login --token {hf_token} 2>&1 | tail -1'" if hf_token
               else "echo \"WARNING: no HF_TOKEN\"'"),
            timeout=30):
            click.echo("FATAL: HF login failed. Aborting.")
            return

        # 7. Docker images (for eval)
        await step("7. Docker images",
            "docker pull affinefoundation/liveweb-arena:latest 2>&1 | tail -1 || echo 'docker pull skipped'")

        # 8. Download model (skip if exists on /data)
        model_dir = f"/data/models/{model.split('/')[-1]}"
        await step(f"8. Download model ({model})",
            f"bash -c '. /data/venv/bin/activate && source /data/.env && "
            f'if [ -f {model_dir}/config.json ]; then echo "Model exists on /data ($(ls {model_dir}/*.safetensors 2>/dev/null | wc -l) shards)"; else '
            f"huggingface-cli download {model} --local-dir {model_dir} --repo-type model 2>&1 | tail -3; fi'",
            timeout=1800)

        # 9. Download data files (skip if exist on /data)
        for f in data_files:
            await step(f"9. Download {f}",
                f"bash -c '. /data/venv/bin/activate && source /data/.env && "
                f'if [ -f /data/datasets/{f} ]; then echo "{f} exists ($(wc -l < /data/datasets/{f}) lines)"; else '
                f"huggingface-cli download {data_repo} {f} --local-dir /data/datasets --repo-type dataset 2>&1 | tail -1 && "
                f"echo {f}: $(wc -l < /data/datasets/{f}) lines; fi'",
                timeout=300)

        # 10. Build combined.jsonl (shuffle + strip extra columns for ms-swift)
        cat_files = " ".join(f"/data/datasets/{f}" for f in data_files)
        await step("10. Build combined.jsonl (shuffle + normalize)",
            f"bash -c 'cat {cat_files} > /data/datasets/combined_raw.jsonl && "
            f". /data/venv/bin/activate && python3 -c \""
            "import json, random; "
            "data = []; "
            "f = open(\\\"/data/datasets/combined_raw.jsonl\\\"); "
            "[data.append(json.loads(l.strip())) for l in f if l.strip()]; "
            "f.close(); "
            "out = []; "
            "[out.append(dict(messages=d[\\\"messages\\\"], **(dict(tools=d[\\\"tools\\\"]) if d.get(\\\"tools\\\") else {}))) for d in data]; "
            "random.seed(42); random.shuffle(out); "
            "f = open(\\\"/data/datasets/combined_shuffled.jsonl\\\", \\\"w\\\"); "
            "[f.write(json.dumps(d, ensure_ascii=False) + \\\"\\\\n\\\") for d in out]; "
            "f.close(); "
            "print(f\\\"combined_shuffled.jsonl: {len(out)} lines (shuffled, normalized)\\\")\"'",
            timeout=120)

        # 11. Verify
        model_dir_short = model.split("/")[-1]
        await step("11. Final verification",
            "bash -c '. /data/venv/bin/activate && "
            "python3 -c \"import torch; print(f\\\"torch={torch.__version__} cuda={torch.cuda.is_available()} gpus={torch.cuda.device_count()}\\\")\" && "
            "python3 -c \"import swift; print(f\\\"ms-swift={swift.__version__}\\\")\" && "
            f"echo Model: $(ls /data/models/{model_dir_short}/*.safetensors 2>/dev/null | wc -l) shards && "
            f"echo Data: $(wc -l < /data/datasets/combined.jsonl) lines && "
            f"echo GPU: $(nvidia-smi -L | wc -l)x $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1) && "
            f"echo Disk: $(df -h /data | tail -1 | awk \"{{print \\$3}}\") used / $(df -h /data | tail -1 | awk \"{{print \\$2}}\") total'")

        click.echo("\n" + "=" * 50)
        click.echo("Setup complete! All persistent data on /data")
        click.echo("  Container rebuild only needs: forge remote -m <m> setup")
        click.echo("  (steps 3-10 will skip — already on /data)")
        click.echo(f"\nReady to train:")
        click.echo(f"  forge train data-summary -m {machine_name}")
        click.echo(f"  forge train launch -m {machine_name}")
        click.echo("=" * 50)

    run_async(_run())


@remote.command(name="clone-eval")
@click.argument("source_machine")
@click.pass_context
def clone_eval(ctx, source_machine):
    """Copy eval infrastructure from another machine.

    \b
    forge remote -m m3 clone-eval m1
    """
    import tempfile, subprocess as sp
    config = ctx.obj["config"]
    backend, src_inst = resolve_machine(config, source_machine)
    _, dst_inst = _get_machine(ctx)

    async def _run():
        with tempfile.TemporaryDirectory() as tmp:
            for path in ["/root/affinetes/", "/root/scripts/", "/root/.env"]:
                click.echo(f"Syncing {path}...")
                try:
                    await backend.download(src_inst, path, f"{tmp}/")
                    await backend.upload(dst_inst, f"{tmp}/{os.path.basename(path.rstrip('/'))}", path)
                except Exception as e:
                    click.echo(f"  WARNING: {path} failed: {e}")

        for img in ["openspiel:eval", "qqr:eval"]:
            click.echo(f"Transferring Docker image {img}...")
            src_addr = f"{src_inst.user}@{src_inst.host}"
            dst_addr = f"{dst_inst.user}@{dst_inst.host}"
            ssh_opts = "-o StrictHostKeyChecking=no -o ConnectTimeout=10"
            result = sp.run(
                f"ssh {ssh_opts} {src_addr} 'docker save {img} | gzip' | "
                f"ssh {ssh_opts} {dst_addr} 'gunzip | docker load'",
                shell=True, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                click.echo(f"  WARNING: {img} failed")

        click.echo("Done!")

    run_async(_run())


@remote.command()
@click.pass_context
def monitor(ctx):
    """Show training progress: step, loss, GPU, ETA.

    \b
    forge remote -m m2 monitor
    """
    backend, inst = _get_machine(ctx)

    def _clean(text):
        return "\n".join(
            l for l in text.strip().split("\n")
            if not l.strip().startswith("Connecting to")
        ).strip()

    async def _run():
        rc, out, _ = await backend.exec(inst,
            "nvidia-smi --query-gpu=index,utilization.gpu,memory.used,memory.total --format=csv,noheader",
            timeout=15)
        if rc == 0:
            click.echo("=== GPU ===")
            for line in _clean(out).split("\n"):
                click.echo(f"  {line.strip()}")

        rc, out, _ = await backend.exec(inst,
            "echo '=== Training ===' && "
            "(pgrep -f train_sft.py > /dev/null && echo 'Status: RUNNING' || echo 'Status: STOPPED') && "
            "echo '=== Progress ===' && "
            "screen -S training -X hardcopy /tmp/screen_out 2>/dev/null; "
            "grep -oP '\\d+/\\d+.*it\\]' /tmp/screen_out 2>/dev/null | tail -1 || echo 'no progress yet' && "
            "echo '=== Loss ===' && "
            "python3 -c \""
            "import json, glob; "
            "files = sorted(glob.glob('/root/checkpoints/checkpoint-*/trainer_state.json')); "
            "print('No checkpoint yet') if not files else ["
            "print(f'  step {e.get(chr(39)+'step'+chr(39),'?')}: loss={e.get(chr(39)+'loss'+chr(39),e.get(chr(39)+'train_loss'+chr(39),'?'))}') "
            "for e in json.load(open(files[-1])).get('log_history',[])[-5:] "
            "if 'loss' in e or 'train_loss' in e]\" 2>/dev/null || echo 'no loss data'",
            timeout=20)
        if rc == 0:
            click.echo(f"\n{_clean(out)}")

    run_async(_run())
