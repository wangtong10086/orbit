"""CLI rental machine subcommands for Affine Forge."""

import asyncio
import os
import click


def run_async(coro):
    """Helper to run async functions from Click commands."""
    return asyncio.run(coro)


@click.group()
@click.option("--machine", "-m", default=None, help="Machine name or index (default: first machine)")
@click.pass_context
def rental(ctx, machine):
    """Remote rental machine management (SSH backend)."""
    ctx.ensure_object(dict)
    ctx.obj["machine_selector"] = machine


def _get_rental(config, machine_selector=None) -> tuple:
    """Load a machine from machines.json, return (SshBackend, GpuInstance).

    Args:
        machine_selector: Machine name or 0-based index. None = first machine.
    """
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

    # Select machine by name or index
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


@rental.command()
@click.pass_context
def status(ctx):
    """Show rental GPU, processes, and training status."""
    config = ctx.obj["config"]
    backend, inst = _get_rental(config, ctx.parent.params.get("machine"))

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
    backend, inst = _get_rental(config, ctx.parent.params.get("machine"))

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
    backend, inst = _get_rental(config, ctx.parent.params.get("machine"))

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
    backend, inst = _get_rental(config, ctx.parent.params.get("machine"))

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


@rental.command(name="upload")
@click.argument("local_path")
@click.argument("remote_path")
@click.pass_context
def upload_file(ctx, local_path, remote_path):
    """Upload a local file/dir to the rental machine via rsync."""
    config = ctx.obj["config"]
    backend, inst = _get_rental(config, ctx.parent.params.get("machine"))

    async def _run():
        click.echo(f"Uploading {local_path} → {remote_path}")
        await backend.upload(inst, local_path, remote_path)
        click.echo("Done.")

    run_async(_run())


@rental.command(name="transfer")
@click.argument("source_machine")
@click.argument("remote_path")
@click.option("--dest-path", default=None, help="Destination path (default: same as source)")
@click.pass_context
def transfer(ctx, source_machine, remote_path, dest_path):
    """Transfer file/dir between machines via local rsync relay.

    Example: forge rental -m m1 transfer m2 /root/merged_model
    """
    import tempfile
    config = ctx.obj["config"]
    backend, src_inst = _get_rental(config, source_machine)
    _, dst_inst = _get_rental(config, ctx.parent.params.get("machine"))
    dst = dest_path or remote_path

    async def _run():
        with tempfile.TemporaryDirectory() as tmp:
            click.echo(f"{src_inst.id}:{remote_path} → {dst_inst.id}:{dst}")
            await backend.download(src_inst, remote_path, f"{tmp}/")
            await backend.upload(dst_inst, f"{tmp}/", os.path.dirname(dst) + "/")
            click.echo("Done.")

    run_async(_run())


def _sglang_env_prefix():
    """Common env setup for sglang: CUDA in PATH, venv, .env, tmp dirs."""
    return (
        "export PATH=/usr/local/cuda/bin:$PATH && "
        "export LD_LIBRARY_PATH=/usr/local/cuda/lib64:/usr/local/cuda-12.8/targets/x86_64-linux/lib:$LD_LIBRARY_PATH && "
        "source /root/venv/bin/activate && "
        "source /root/.env && "
        "export TMPDIR=/root/tmp TRITON_CACHE_DIR=/root/.triton_cache && "
    )


@rental.command(name="start-sglang")
@click.argument("model")
@click.option("--port", default=30000, type=int)
@click.option("--tp", default=4, type=int)
@click.option("--dp", default=1, type=int, help="Data parallelism (number of dp replicas)")
@click.option("--mem-frac", default=0.80, type=float, help="GPU memory fraction for KV cache (0.80 leaves room for eval Docker)")
@click.option("--wait/--no-wait", default=True, help="Wait for server to be ready (default: yes)")
@click.pass_context
def start_sglang(ctx, model, port, tp, dp, mem_frac, wait):
    """Start sglang inference server on rental. Kills existing sglang first."""
    import time as time_mod
    config = ctx.obj["config"]
    backend, inst = _get_rental(config, ctx.parent.params.get("machine"))

    async def _run():
        # Kill existing sglang
        await backend.exec(inst, "pkill -9 -f sglang 2>/dev/null; screen -S sglang -X quit 2>/dev/null; sleep 2", timeout=15)

        dp_flag = f"--dp {dp} " if dp > 1 else ""
        cmd = (
            f"screen -dmS sglang bash -c '"
            f"{_sglang_env_prefix()}"
            f"python3 -m sglang.launch_server "
            f"--model-path {model} --port {port} --host 0.0.0.0 --tp {tp} "
            f"{dp_flag}"
            f"--trust-remote-code --disable-cuda-graph --disable-radix-cache "
            f"--tool-call-parser qwen25 "
            f"--mem-fraction-static {mem_frac} "
            f"2>&1 | tee /root/logs/sglang.log"
            f"'"
        )
        click.echo(f"Starting sglang with {model} (tp={tp}, dp={dp}, mem={mem_frac})...")
        rc, _, err = await backend.exec(inst, cmd, timeout=15)
        if rc != 0:
            raise click.ClickException(f"Failed: {err}")

        if wait:
            click.echo("Waiting for sglang to be ready...")
            for i in range(24):  # 24 * 15s = 6 min max
                time_mod.sleep(15)
                rc, out, _ = await backend.exec(inst, f"curl -s -m 5 http://127.0.0.1:{port}/v1/models 2>/dev/null", timeout=10)
                if rc == 0 and out and "model" in out:
                    click.echo(f"sglang ready after {(i+1)*15}s")
                    # Verify Docker bridge connectivity
                    rc2, out2, _ = await backend.exec(inst, f"curl -s -m 5 http://172.17.0.1:{port}/v1/models 2>/dev/null", timeout=10)
                    if rc2 == 0 and out2 and "model" in out2:
                        click.echo("Docker bridge (172.17.0.1) connectivity: OK")
                    else:
                        click.echo("WARNING: Docker bridge (172.17.0.1) not reachable — eval containers may fail")
                    return
                # Check if sglang crashed
                rc3, _, _ = await backend.exec(inst, "screen -ls | grep -q sglang", timeout=5)
                if rc3 != 0:
                    rc4, log, _ = await backend.exec(inst, "tail -5 /root/logs/sglang.log 2>/dev/null", timeout=5)
                    raise click.ClickException(f"sglang crashed during startup:\n{log}")
            raise click.ClickException("sglang did not become ready within 6 minutes")
        click.echo(f"sglang started on port {port}. Check: forge rental exec 'curl -s http://127.0.0.1:{port}/health'")

    run_async(_run())


@rental.command(name="start-eval")
@click.argument("model")
@click.option("--envs", default="GAME,NAVWORLD,SWE-INFINITE,LIVEWEB", help="Comma-separated envs")
@click.option("--samples", default=100, type=int)
@click.option("--base-url", default="http://172.17.0.1:30000/v1")
@click.pass_context
def start_eval(ctx, model, envs, samples, base_url):
    """Start multi-env evaluation on rental."""
    config = ctx.obj["config"]
    backend, inst = _get_rental(config, ctx.parent.params.get("machine"))

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


@rental.command(name="monitor")
@click.pass_context
def monitor(ctx):
    """Show training progress: step, loss, GPU, ETA."""
    config = ctx.obj["config"]
    backend, inst = _get_rental(config, ctx.parent.params.get("machine"))

    def _clean(text):
        """Strip SSH connection messages from output."""
        return "\n".join(
            l for l in text.strip().split("\n")
            if not l.strip().startswith("Connecting to")
        ).strip()

    async def _run():
        # 1. GPU status
        rc, out, _ = await backend.exec(inst,
            "nvidia-smi --query-gpu=index,utilization.gpu,memory.used,memory.total --format=csv,noheader",
            timeout=15)
        if rc == 0:
            click.echo("=== GPU ===")
            for line in _clean(out).split("\n"):
                click.echo(f"  {line.strip()}")

        # 2. Training process + step in one call
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
        else:
            # Fallback: just show log tail
            rc2, out2, _ = await backend.exec(inst, "tail -5 /root/training.log 2>/dev/null", timeout=10)
            if rc2 == 0:
                click.echo(f"\nLast log:\n{_clean(out2)}")

    run_async(_run())



@rental.command(name="setup")
@click.pass_context
def setup(ctx):
    """One-key full setup: system libs, CUDA toolkit, venv, training+inference stack, Docker images.

    After setup + clone-eval, machine is ready for both training and evaluation.
    """
    config = ctx.obj["config"]
    backend, inst = _get_rental(config, ctx.parent.params.get("machine"))

    async def _run():
        steps = [
            ("System packages (libnuma, docker, gpg, screen, git, curl)",
             "apt-get update -qq && apt-get install -y -qq "
             "python3 python3-pip python3-venv screen git curl "
             "libnuma1 libnuma-dev docker.io gpg 2>&1 | tail -3"),

            ("CUDA toolkit (nvcc + cudart-dev — required by deep_gemm/sglang)",
             "bash -c '"
             'if [ -f /usr/local/cuda/bin/nvcc ]; then echo "CUDA toolkit already installed"; exit 0; fi; '
             "curl -fsSL https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/3bf863cc.pub "
             "| gpg --dearmor -o /usr/share/keyrings/cuda-archive-keyring.gpg 2>/dev/null; "
             'echo "deb [signed-by=/usr/share/keyrings/cuda-archive-keyring.gpg] '
             'https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/ /" '
             "> /etc/apt/sources.list.d/cuda-ubuntu2404-x86_64.list; "
             "apt-get update -qq 2>&1 | tail -1; "
             "apt-get install -y --no-install-recommends cuda-nvcc-12-8 cuda-cudart-dev-12-8 2>&1 | tail -3; "
             "ln -sf /usr/local/cuda-12.8 /usr/local/cuda 2>/dev/null; "
             "echo CUDA_INSTALLED"
             "'"),

            ("Venv + directories",
             "bash -c '"
             "python3 -m venv /root/venv 2>/dev/null; "
             ". /root/venv/bin/activate && pip install --upgrade pip 2>&1 | tail -1; "
             "mkdir -p /root/checkpoints /root/data /root/scripts /root/logs /root/tmp; "
             "echo dirs_created"
             "'"),

            ("ML training stack (torch, transformers, peft, trl, bitsandbytes)",
             "bash -c '. /root/venv/bin/activate && "
             "pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124 2>&1 | tail -3 && "
             "pip install transformers datasets accelerate peft trl bitsandbytes huggingface_hub 2>&1 | tail -3'"),

            ("sglang inference stack + eval deps",
             "bash -c '. /root/venv/bin/activate && "
             "pip install \"sglang[all]\" nest_asyncio docker openai httpx 2>&1 | tail -5'"),

            ("Docker images (liveweb-arena)",
             "docker pull affinefoundation/liveweb-arena:latest 2>&1 | tail -1"),

            ("Verify full stack",
             "bash -c '. /root/venv/bin/activate && "
             "export PATH=/usr/local/cuda/bin:$PATH && "
             "python3 -c \""
             "import torch; print(f\\\"torch={torch.__version__}, cuda={torch.cuda.is_available()}, gpus={torch.cuda.device_count()}\\\"); "
             "import sglang; print(f\\\"sglang={sglang.__version__}\\\"); "
             "from deep_gemm.utils.layout import get_mn_major_tma_aligned_tensor; print(\\\"deep_gemm=OK\\\"); "
             "\"'"),
        ]

        for desc, cmd in steps:
            click.echo(f"\n=== {desc} ===")
            rc, out, err = await backend.exec(inst, cmd, timeout=600)
            if out:
                click.echo(out.strip())
            if rc != 0:
                click.echo(f"  WARNING: {desc} had errors (rc={rc})")
                if err:
                    click.echo(f"  {err[:300]}")

        click.echo("\n=== Setup complete ===")
        click.echo("Next: forge rental -m <this> clone-eval <source_machine>")

    run_async(_run())


@rental.command(name="clone-eval")
@click.argument("source_machine")
@click.pass_context
def clone_eval(ctx, source_machine):
    """Copy eval infra (affinetes + scripts + .env + Docker images) from source machine.

    Usage: forge rental -m m2 clone-eval m1
    """
    import tempfile
    config = ctx.obj["config"]
    backend, src_inst = _get_rental(config, source_machine)
    _, dst_inst = _get_rental(config, ctx.parent.params.get("machine"))

    async def _run():
        with tempfile.TemporaryDirectory() as tmp:
            # rsync eval files via local relay
            for path in ["/root/affinetes/", "/root/scripts/", "/root/.env"]:
                click.echo(f"Syncing {path}...")
                try:
                    await backend.download(src_inst, path, f"{tmp}/")
                    await backend.upload(dst_inst, f"{tmp}/{os.path.basename(path.rstrip('/'))}", path)
                except Exception as e:
                    click.echo(f"  WARNING: {path} failed: {e}")

        # Docker images (not on Hub, must transfer)
        for img in ["openspiel:eval", "qqr:eval"]:
            click.echo(f"Transferring Docker image {img}...")
            src_addr = f"{src_inst.user}@{src_inst.host}"
            dst_addr = f"{dst_inst.user}@{dst_inst.host}"
            ssh_opts = "-o StrictHostKeyChecking=no -o ConnectTimeout=10"
            import subprocess as sp
            result = sp.run(
                f"ssh {ssh_opts} {src_addr} 'docker save {img} | gzip' | "
                f"ssh {ssh_opts} {dst_addr} 'gunzip | docker load'",
                shell=True, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                click.echo(f"  WARNING: {img} failed")

        click.echo("Done!")

    run_async(_run())


# -- LIVEWEB tool_call normalization for Qwen3 chat template --
# Qwen3 apply_chat_template produces:
#   assistant: <tool_call>\n{"name": "...", "arguments": {...}}\n</tool_call>
#   tool response: role=user with <tool_response>\n...\n</tool_response>
#   system: includes # Tools\n<tools>...\n</tools> section
# We replicate this format so SFTTrainer training matches eval inference.

# Browser action tool definitions matching liveweb-arena eval
_LIVEWEB_TOOLS = [
    {"type": "function", "function": {"name": "goto", "description": "Navigate to a URL", "parameters": {"type": "object", "properties": {"url": {"type": "string", "description": "URL to navigate to"}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "click", "description": "Click an element by CSS selector", "parameters": {"type": "object", "properties": {"selector": {"type": "string", "description": "CSS selector"}}, "required": ["selector"]}}},
    {"type": "function", "function": {"name": "type", "description": "Type text into an input field", "parameters": {"type": "object", "properties": {"selector": {"type": "string"}, "text": {"type": "string"}, "press_enter": {"type": "boolean"}}, "required": ["selector", "text"]}}},
    {"type": "function", "function": {"name": "scroll", "description": "Scroll the page", "parameters": {"type": "object", "properties": {"direction": {"type": "string", "enum": ["up", "down"]}, "amount": {"type": "integer"}}, "required": ["direction"]}}},
    {"type": "function", "function": {"name": "stop", "description": "Complete task and submit final answers", "parameters": {"type": "object", "properties": {"answers": {"type": "object", "description": "Answer key-value pairs"}}, "required": ["answers"]}}},
    {"type": "function", "function": {"name": "click_role", "description": "Click by accessibility role and name", "parameters": {"type": "object", "properties": {"role": {"type": "string"}, "name": {"type": "string"}, "exact": {"type": "boolean"}}, "required": ["role", "name"]}}},
    {"type": "function", "function": {"name": "type_role", "description": "Type by accessibility role", "parameters": {"type": "object", "properties": {"role": {"type": "string"}, "text": {"type": "string"}, "name": {"type": "string"}, "press_enter": {"type": "boolean"}}, "required": ["role", "text"]}}},
    {"type": "function", "function": {"name": "press", "description": "Press a keyboard key", "parameters": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}}},
    {"type": "function", "function": {"name": "wait", "description": "Wait for a duration", "parameters": {"type": "object", "properties": {"seconds": {"type": "integer"}}, "required": []}}},
    {"type": "function", "function": {"name": "view_more", "description": "View more truncated content", "parameters": {"type": "object", "properties": {"direction": {"type": "string", "enum": ["up", "down"]}}, "required": ["direction"]}}},
]


def _normalize_tool_calls_qwen3(messages, json_mod):
    """Convert OpenAI-format tool_calls to Qwen3 native <tool_call> XML tags.

    Matches the output of Qwen3 tokenizer.apply_chat_template(messages, tools=...).
    """
    # Build tools section for system prompt
    tools_text = "\n\n# Tools\n\nYou may call one or more functions to assist with the user query.\n\n"
    tools_text += "You are provided with function signatures within <tools></tools> XML tags:\n<tools>\n"
    for tool in _LIVEWEB_TOOLS:
        tools_text += json_mod.dumps(tool, ensure_ascii=False) + "\n"
    tools_text += "</tools>\n\n"
    tools_text += 'For each function call, return a json object with function name and arguments within <tool_call></tool_call> XML tags:\n'
    tools_text += '<tool_call>\n{"name": <function-name>, "arguments": <args-json-object>}\n</tool_call>'

    normalized = []
    for msg in messages:
        role = msg["role"]
        content = msg.get("content", "") or ""

        if role == "system":
            # Append tool definitions to system prompt
            normalized.append({"role": "system", "content": content + tools_text})

        elif role == "assistant" and msg.get("tool_calls"):
            # Convert tool_calls to <tool_call> XML tags
            tc_parts = []
            for tc in msg["tool_calls"]:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                # Parse arguments: may be string or dict
                args = fn.get("arguments", "{}")
                if isinstance(args, str):
                    try:
                        args = json_mod.loads(args)
                    except (json_mod.JSONDecodeError, TypeError):
                        args = {}
                tc_parts.append(
                    f'<tool_call>\n{json_mod.dumps({"name": name, "arguments": args}, ensure_ascii=False)}\n</tool_call>'
                )
            tc_content = "\n".join(tc_parts)
            # Prepend any existing content (thinking, etc.)
            full_content = (content + "\n" + tc_content).strip() if content else tc_content
            normalized.append({"role": "assistant", "content": full_content})

        elif role == "tool":
            # Convert tool response: role → user, wrap in <tool_response>
            normalized.append({
                "role": "user",
                "content": f"<tool_response>\n{content}\n</tool_response>",
            })

        else:
            normalized.append({"role": role, "content": content})

    return normalized


@rental.command(name="prepare-data")
@click.option("--data-dir", default="data/canonical", help="Local data directory")
@click.option("--envs", default="GAME,NAVWORLD,SWE-INFINITE,LIVEWEB", help="Environments to include")
@click.option("--remote-path", default="/root/data/combined.jsonl", help="Remote destination path")
@click.pass_context
def prepare_data(ctx, data_dir, envs, remote_path):
    """Combine local env data files, normalize schema, and upload to rental."""
    import json as json_mod
    import tempfile

    config = ctx.obj["config"]
    backend, inst = _get_rental(config, ctx.parent.params.get("machine"))

    env_files = {
        "GAME": "game.jsonl",
        "NAVWORLD": "navworld.jsonl",
        "SWE-INFINITE": "swe_infinite.jsonl",
        "SWE-INFINITE": "swe_infinite.jsonl",
        "LIVEWEB": "liveweb.jsonl",
        "LGC-v2": "lgc_v2.jsonl",
        "PRINT": "print.jsonl",
    }

    data_path = config.project_root / data_dir
    env_list = [e.strip() for e in envs.split(",")]
    total = 0
    lines = []

    for env in env_list:
        fname = env_files.get(env)
        if not fname:
            raise click.ClickException(f"Unknown env: {env}")
        fpath = data_path / fname
        if not fpath.exists():
            raise click.ClickException(f"File not found: {fpath}")
        count = 0
        with open(fpath) as f:
            for line in f:
                d = json_mod.loads(line)
                has_tool_calls = any(
                    m.get("tool_calls") for m in d["messages"]
                )
                if has_tool_calls:
                    # Qwen3-native format: convert OpenAI tool_calls to
                    # <tool_call> XML tags that match apply_chat_template output.
                    # This ensures training format matches eval inference format.
                    normalized = _normalize_tool_calls_qwen3(d["messages"], json_mod)
                else:
                    # Standard envs (no tool_calls): keep {role, content} only
                    normalized = []
                    for msg in d["messages"]:
                        normalized.append({
                            "role": msg["role"],
                            "content": msg.get("content", "") or "",
                        })
                lines.append(json_mod.dumps({"messages": normalized}, ensure_ascii=False))
                count += 1
        click.echo(f"  {env}: {count} samples")
        total += count

    click.echo(f"  Total: {total} samples")

    # Write to temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write("\n".join(lines) + "\n")
        tmp_path = f.name

    async def _run():
        click.echo(f"Uploading to {remote_path}...")
        await backend.upload(inst, tmp_path, remote_path)
        os.unlink(tmp_path)
        rc, out, _ = await backend.exec(inst, f"wc -l {remote_path}", timeout=10)
        if rc == 0:
            click.echo(f"Done: {out.strip()}")

    run_async(_run())


@rental.command(name="eval-pipeline")
@click.option("--model", default="/root/merged_model", help="Model path on remote")
@click.option("--checkpoint", default=None, help="LoRA checkpoint to merge (skip if merged model exists)")
@click.option("--envs", default="GAME,NAVWORLD,SWE-INFINITE,LIVEWEB", help="Comma-separated envs")
@click.option("--samples", default=100, type=int)
@click.option("--tp", default=4, type=int)
@click.option("--port", default=30000, type=int)
@click.pass_context
def eval_pipeline(ctx, model, checkpoint, envs, samples, tp, port):
    """One-command eval: kill old → (merge LoRA) → fix env → deploy sglang → wait ready → start eval."""
    import time as time_mod
    config = ctx.obj["config"]
    backend, inst = _get_rental(config, ctx.parent.params.get("machine"))

    async def _run():
        base_url = f"http://172.17.0.1:{port}/v1"

        # Step 1: Kill existing sglang/eval
        click.echo("Step 1/5: Cleaning up old processes...")
        await backend.exec(inst,
            "pkill -9 -f sglang 2>/dev/null; pkill -9 -f eval_envs 2>/dev/null; "
            "screen -S sglang -X quit 2>/dev/null; screen -S eval -X quit 2>/dev/null; sleep 2",
            timeout=15)

        # Step 2: Fix CUDA env (ensure libcudart.so symlink)
        click.echo("Step 2/5: Ensuring CUDA env...")
        await backend.exec(inst,
            "test -f /usr/local/cuda/lib64/libcudart.so || "
            "ln -sf /usr/local/cuda-12.8/targets/x86_64-linux/lib/libcudart.so /usr/local/cuda/lib64/libcudart.so",
            timeout=10)

        # Step 3: Merge LoRA if checkpoint specified
        if checkpoint:
            click.echo(f"Step 3/5: Merging LoRA from {checkpoint}...")
            rc, out, err = await backend.exec(inst,
                f"{_sglang_env_prefix()} python3 /root/scripts/merge_lora.py {checkpoint} {model}",
                timeout=600)
            if rc != 0:
                raise click.ClickException(f"LoRA merge failed: {err}")
            click.echo(f"  Merged: {out.strip().split(chr(10))[-1]}")
        else:
            click.echo("Step 3/5: Skipping merge (using existing merged model)")

        # Step 4: Deploy sglang
        click.echo(f"Step 4/5: Deploying sglang (tp={tp})...")
        cmd = (
            f"screen -dmS sglang bash -c '"
            f"{_sglang_env_prefix()}"
            f"python3 -m sglang.launch_server "
            f"--model-path {model} --port {port} --host 0.0.0.0 --tp {tp} "
            f"--trust-remote-code --disable-cuda-graph --disable-radix-cache "
            f"--tool-call-parser qwen25 "
            f"--mem-fraction-static 0.88 "
            f"2>&1 | tee /root/logs/sglang.log"
            f"'"
        )
        rc, _, err = await backend.exec(inst, cmd, timeout=15)
        if rc != 0:
            raise click.ClickException(f"sglang launch failed: {err}")

        # Wait for sglang to be ready (poll health endpoint)
        click.echo("  Waiting for sglang to be ready", nl=False)
        for i in range(60):  # up to 5 minutes
            await asyncio.sleep(5)
            rc, out, _ = await backend.exec(inst,
                f"curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:{port}/health 2>/dev/null || echo 000",
                timeout=10)
            code = out.strip().replace("'", "")
            if code == "200":
                click.echo(" READY!")
                break
            # Check for crash
            rc2, log_tail, _ = await backend.exec(inst, "tail -2 /root/logs/sglang.log 2>/dev/null", timeout=5)
            if "SIGQUIT" in (log_tail or "") or "exception" in (log_tail or "").lower():
                click.echo(" FAILED!")
                raise click.ClickException(f"sglang crashed. Check: forge rental exec 'tail -20 /root/logs/sglang.log'")
            click.echo(".", nl=False)
        else:
            click.echo(" TIMEOUT!")
            raise click.ClickException("sglang failed to start within 5 minutes")

        # Step 5: Start eval
        click.echo(f"Step 5/5: Starting eval ({envs} × {samples} samples)...")
        env_list = envs.replace(",", " ")
        eval_cmd = (
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
        rc, _, err = await backend.exec(inst, eval_cmd, timeout=15)
        if rc != 0:
            raise click.ClickException(f"Eval launch failed: {err}")

        click.echo("\nEval pipeline running! Monitor with:")
        click.echo("  forge rental exec 'tail -20 /root/logs/eval.log'")

    run_async(_run())


@rental.command(name="clean-data")
@click.argument("dataset_path")
@click.option("--remove-envs", default="LGC-v2,PRINT", help="Envs to remove (comma-separated)")
@click.option("-o", "--output", default=None, help="Output path (default: overwrite input)")
@click.pass_context
def clean_data(ctx, dataset_path, remove_envs, output):
    """Remove unwanted environment data from a dataset on rental."""
    config = ctx.obj["config"]
    backend, inst = _get_rental(config, ctx.parent.params.get("machine"))
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


# ---------------------------------------------------------------------------
# Sync & Run — efficient remote development workflow
# ---------------------------------------------------------------------------

_SYNC_PATHS = ["scripts/", "forge/", "knowledge/", "experiments/"]
_REMOTE_BASE = "/root/project"


@rental.command(name="sync")
@click.option("--paths", "-p", multiple=True, help="Local paths to sync (default: scripts/ forge/)")
@click.option("--remote-base", default=_REMOTE_BASE, help="Remote base directory")
@click.option("--delete/--no-delete", default=False, help="Delete remote files not in local")
@click.pass_context
def sync_cmd(ctx, paths, remote_base, delete):
    """Sync local project files to GPU machine via rsync."""
    config = ctx.obj["config"]
    backend, inst = _get_rental(config, ctx.parent.params.get("machine"))
    sync_paths = list(paths) if paths else _SYNC_PATHS

    async def _run():
        await backend.exec(inst, f"mkdir -p {remote_base}", timeout=10)
        for local_path in sync_paths:
            if not os.path.exists(local_path):
                continue
            remote_path = f"{remote_base}/{local_path}"
            await backend.exec(inst, f"mkdir -p {os.path.dirname(remote_path.rstrip('/'))}", timeout=5)
            ssh_opts = "ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10"
            remote_target = f"{inst.user}@{inst.host}:{remote_path}"
            cmd = ["rsync", "-az", "-e", ssh_opts, local_path, remote_target]
            if delete:
                cmd.insert(2, "--delete")
            click.echo(f"  {local_path} → {remote_target}")
            await backend.upload(inst, local_path, remote_path)
        click.echo("Sync complete.")

    run_async(_run())


@rental.command(name="run")
@click.argument("command")
@click.option("--sync/--no-sync", "auto_sync", default=True, help="Auto-sync before running")
@click.option("--bg/--fg", "background", default=False, help="Run in background via nohup")
@click.option("--log", default=None, help="Background log file")
@click.option("--cwd", default=_REMOTE_BASE, help="Remote working directory")
@click.pass_context
def run_cmd(ctx, command, auto_sync, background, log, cwd):
    """Sync + run command on GPU. Examples:
    forge rental run "python3 scripts/game/test3.py leduc_poker"
    forge rental run --bg "python3 scripts/game/test3.py othello"
    """
    config = ctx.obj["config"]
    backend, inst = _get_rental(config, ctx.parent.params.get("machine"))

    async def _run():
        if auto_sync:
            click.echo("Syncing...")
            await backend.exec(inst, f"mkdir -p {cwd}", timeout=10)
            for p in _SYNC_PATHS:
                if os.path.exists(p):
                    import subprocess
                    await backend.upload(inst, p, f"{cwd}/{p}")

        env = f"cd {cwd} && PYTHONPATH={cwd}/scripts:{cwd}/scripts/game OPENSPIEL_DIR=/root/affinetes/environments/openspiel"
        if background:
            log_path = log or "/root/run.log"
            full_cmd = f"{env} nohup {command} > {log_path} 2>&1 & echo 'PID: $!'"
            rc, out, _ = await backend.exec(inst, full_cmd, timeout=15)
        else:
            full_cmd = f"{env} {command}"
            rc, out, err = await backend.exec(inst, full_cmd, timeout=600)
        if out:
            click.echo(out.rstrip())

    run_async(_run())


@rental.command(name="game-test")
@click.argument("game", required=False)
@click.option("-n", default=3, help="Number of games")
@click.option("--all", "all_games", is_flag=True, help="Test all 7 games")
@click.pass_context
def game_test(ctx, game, n, all_games):
    """Test game bot vs MCTS. Auto-syncs scripts first.
    forge rental game-test leduc_poker
    forge rental game-test --all
    """
    config = ctx.obj["config"]
    backend, inst = _get_rental(config, ctx.parent.params.get("machine"))
    games = ["goofspiel", "leduc_poker", "liars_dice", "gin_rummy", "othello", "hex", "clobber"]
    test_games = games if all_games else ([game] if game else [])
    if not test_games:
        raise click.UsageError("Specify game or --all")

    async def _run():
        # Sync scripts
        click.echo("Syncing scripts...")
        import subprocess
        ssh_opts = "ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10"
        for p in ["scripts/"]:
            if os.path.exists(p):
                await backend.exec(inst, f"mkdir -p {_REMOTE_BASE}/{p}", timeout=5)
                await backend.upload(inst, p, f"{_REMOTE_BASE}/{p}")

        for g in test_games:
            cmd = (f"cd {_REMOTE_BASE} && "
                   f"PYTHONPATH={_REMOTE_BASE}/scripts:{_REMOTE_BASE}/scripts/game "
                   f"OPENSPIEL_DIR=/root/affinetes/environments/openspiel "
                   f"nohup python3 scripts/game/test3.py {g} $RANDOM {n} "
                   f"> /root/game_test_{g}.txt 2>&1 & echo '{g} started'")
            rc, out, _ = await backend.exec(inst, cmd, timeout=15)
            click.echo(f"  {out.strip()}" if out else f"  {g}: failed")

    run_async(_run())


@rental.command(name="game-status")
@click.pass_context
def game_status(ctx):
    """Check all game test results."""
    config = ctx.obj["config"]
    backend, inst = _get_rental(config, ctx.parent.params.get("machine"))

    async def _run():
        games = "goofspiel leduc_poker liars_dice gin_rummy othello hex clobber"
        rc, out, _ = await backend.exec(inst,
            f"for g in {games}; do r=$(grep '^RESULT' /root/game_test_${{g}}.txt 2>/dev/null); "
            f"echo \"  $g: ${{r:-running}}\"; done", timeout=15)
        click.echo(out.rstrip() if out else "No results")

    run_async(_run())


@rental.command(name="game-analyze")
@click.argument("game")
@click.pass_context
def game_analyze(ctx, game):
    """Show full detail for a game test."""
    config = ctx.obj["config"]
    backend, inst = _get_rental(config, ctx.parent.params.get("machine"))

    async def _run():
        rc, out, _ = await backend.exec(inst,
            f"cat /root/game_test_{game}.txt 2>/dev/null || echo 'No results'", timeout=15)
        click.echo(out.rstrip())

    run_async(_run())
