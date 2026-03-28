"""CLI training subcommands for Affine Forge.

Commands:
    forge train setup -m <machine>           # Full machine setup (venv, model, data)
    forge train data-summary -m <machine>    # Analyze training data on remote machine
    forge train launch -m <machine>          # Launch ms-swift training
    forge train monitor -m <machine>         # Monitor running training
    forge train stop -m <machine>            # Stop training
"""

import asyncio
import json
import os
from pathlib import Path

import click


def run_async(coro):
    return asyncio.run(coro)


@click.group()
def train():
    """Training pipeline commands (ms-swift on remote machines)."""
    pass


# ===== Setup =====

@train.command()
@click.option("-m", "--machine", required=True, help="Machine name")
@click.option("--model", default="Qwen/Qwen3-32B", help="Model to download")
@click.option("--data-repo", default="monokoco/affine-sft-data", help="HF dataset repo")
@click.option("--data-files", default="game.jsonl,navworld.jsonl,liveweb.jsonl,swe_infinite.jsonl,memorygym.jsonl",
              help="Comma-separated data files to download")
@click.pass_context
def setup(ctx, machine, model, data_repo, data_files):
    """Full machine setup: system packages, venv, ms-swift, model, data.

    \b
    forge train setup -m m3
    forge train setup -m m3 --model Qwen/Qwen3-32B
    """
    from forge.cli_remote import resolve_machine
    from forge.config import ForgeConfig

    config = ctx.obj["config"]
    backend, inst = resolve_machine(config, machine)

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

    files_list = [f.strip() for f in data_files.split(",") if f.strip()]

    async def _run():
        async def step(desc, cmd, timeout=600):
            click.echo(f"\n[{desc}]")
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

        # 1. System packages
        await step("System packages",
            "export DEBIAN_FRONTEND=noninteractive && "
            "apt-get update -qq && "
            "apt-get install -y -qq python3 python3-venv python3-pip git screen curl wget build-essential > /dev/null 2>&1 && "
            "python3 --version")

        # 2. Venv
        await step("Venv + pip",
            "python3 -m venv /root/venv && "
            ". /root/venv/bin/activate && "
            "pip install -q --upgrade pip && "
            "echo 'venv ready'")

        # 3. ML stack (torch + ms-swift + deepspeed)
        await step("ML stack (torch + ms-swift + deepspeed)",
            ". /root/venv/bin/activate && "
            "pip install -q torch torchvision torchaudio && "
            "pip install -q 'ms-swift[llm]>=4.0' deepspeed accelerate && "
            "pip install -q sglang[all] huggingface_hub && "
            "python3 -c 'import torch; print(f\"torch={torch.__version__} cuda={torch.cuda.is_available()}\")'",
            timeout=600)

        # 4. Flash-attn (optional, may fail)
        await step("flash-attn (optional)",
            ". /root/venv/bin/activate && "
            "pip install -q flash-attn --no-build-isolation 2>&1 | tail -1 || echo 'flash-attn skipped (will use sdpa)'",
            timeout=300)

        # 5. Directories
        await step("Directories",
            "mkdir -p /root/{data,models,checkpoints,logs,scripts,configs} && echo 'dirs created'",
            timeout=10)

        # 6. .env with tokens
        env_content = f"export HF_TOKEN={hf_token}\\nexport AMAP_API_KEY={amap_key}\\nexport AMAP_MAPS_API_KEY={amap_maps_key}"
        await step("Write .env",
            f'printf "{env_content}\\n" > /root/.env && echo ".env written"',
            timeout=10)

        # 7. HF login
        if hf_token:
            await step("HF login",
                f". /root/venv/bin/activate && "
                f"huggingface-cli login --token {hf_token} 2>&1 | tail -1",
                timeout=30)

        # 8. Download model
        model_dir = f"/root/models/{model.split('/')[-1]}"
        await step(f"Download model ({model})",
            f". /root/venv/bin/activate && source /root/.env && "
            f"huggingface-cli download {model} --local-dir {model_dir} --repo-type model 2>&1 | tail -3 && "
            f"echo 'Shards:' $(ls {model_dir}/*.safetensors 2>/dev/null | wc -l)",
            timeout=1800)

        # 9. Download data files
        for f in files_list:
            await step(f"Download {f}",
                f". /root/venv/bin/activate && source /root/.env && "
                f"huggingface-cli download {data_repo} {f} --local-dir /root/data --repo-type dataset 2>&1 | tail -1 && "
                f"echo $(wc -l < /root/data/{f}) lines",
                timeout=300)

        # 10. Build combined.jsonl
        cat_cmd = " ".join(f"/root/data/{f}" for f in files_list)
        await step("Build combined.jsonl",
            f"cat {cat_cmd} > /root/data/combined.jsonl && "
            f"echo 'combined.jsonl:' $(wc -l < /root/data/combined.jsonl) 'lines'",
            timeout=60)

        # 11. Verify
        await step("Verify",
            ". /root/venv/bin/activate && "
            f"python3 -c 'import torch; print(f\"torch={{torch.__version__}} cuda={{torch.cuda.is_available()}} gpus={{torch.cuda.device_count()}}\")' && "
            f"echo 'Model:' $(ls {model_dir}/*.safetensors 2>/dev/null | wc -l) 'shards' && "
            f"echo 'Data:' $(wc -l < /root/data/combined.jsonl) 'lines' && "
            f"echo 'GPU:' $(nvidia-smi -L | wc -l) 'x' $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)",
            timeout=30)

        click.echo("\n" + "=" * 50)
        click.echo("Setup complete! Next steps:")
        click.echo(f"  forge train data-summary -m {machine}")
        click.echo(f"  forge train launch -m {machine}")
        click.echo("=" * 50)

    run_async(_run())


# ===== Data Summary =====

@train.command(name="data-summary")
@click.option("-m", "--machine", required=True, help="Machine name from machines.json")
@click.option("--data", default="/data/datasets/combined.jsonl", help="Path to JSONL on remote")
@click.pass_context
def data_summary(ctx, machine, data):
    """Analyze training data on remote machine: env distribution, format checks, token stats."""
    from forge.cli_remote import resolve_machine

    config = ctx.obj["config"]
    backend, inst = resolve_machine(config, machine)

    script = r'''python3 -c "
import json, sys
total = 0
by_env = {}
issues = {'last_not_assistant': 0, 'empty': 0, 'has_tool_calls': 0, 'has_tools_field': 0}
char_lengths = []
with open('DATA_PATH') as f:
    for line in f:
        d = json.loads(line.strip())
        msgs = d.get('messages', [])
        env = d.get('env', 'unknown')
        total += 1
        by_env[env] = by_env.get(env, 0) + 1
        if not msgs:
            issues['empty'] += 1
            continue
        if msgs[-1].get('role') != 'assistant':
            issues['last_not_assistant'] += 1
        if any(m.get('tool_calls') for m in msgs):
            issues['has_tool_calls'] += 1
        if d.get('tools'):
            issues['has_tools_field'] += 1
        char_lengths.append(sum(len(m.get('content','') or '') for m in msgs))

print(f'Total samples: {total}')
print(f'')
print('By environment:')
for e in sorted(by_env, key=lambda x: -by_env[x]):
    pct = by_env[e]/total*100
    print(f'  {e:20s} {by_env[e]:>6d}  ({pct:.1f}%)')
print(f'')
print('Format checks:')
for k,v in issues.items():
    flag = 'WARNING' if v > 0 and k in ('last_not_assistant','empty') else 'ok'
    print(f'  {k:25s} {v:>6d}  {flag}')
print(f'')
if char_lengths:
    char_lengths.sort()
    n = len(char_lengths)
    print(f'Char length stats (proxy for tokens):')
    print(f'  min={char_lengths[0]}, median={char_lengths[n//2]}, mean={sum(char_lengths)//n}')
    print(f'  p95={char_lengths[int(n*0.95)]}, max={char_lengths[-1]}')
"
'''.replace("DATA_PATH", data)

    async def _run():
        rc, out, err = await backend.exec(inst, script, timeout=120)
        click.echo(out)
        if err:
            click.echo(err, err=True)

    run_async(_run())


# ===== Launch Training =====

@train.command()
@click.option("-m", "--machine", required=True, help="Machine name")
@click.option("--data", default="/data/datasets/combined_shuffled.jsonl", help="JSONL path on remote")
@click.option("--model", default="/data/models/Qwen3-32B", help="Model path on remote")
@click.option("--output", default="/data/checkpoints", help="Output dir on remote")
@click.option("--train-type", default="full", type=click.Choice(["full", "lora"]), help="Training type")
@click.option("--deepspeed", default="zero3", help="DeepSpeed stage (zero2/zero3)")
@click.option("--batch-size", default=1, type=int, help="Per-device batch size")
@click.option("--grad-accum", default=4, type=int, help="Gradient accumulation steps")
@click.option("--lr", default=2e-5, type=float, help="Learning rate")
@click.option("--seq-len", default=32768, type=int, help="Max sequence length")
@click.option("--epochs", default=1, type=int, help="Number of epochs")
@click.option("--save-steps", default=50, type=int, help="Save checkpoint every N steps")
@click.option("--save-limit", default=5, type=int, help="Max checkpoints to keep")
@click.option("--extra-args", default="", help="Additional swift sft arguments")
@click.pass_context
def launch(ctx, machine, data, model, output, train_type, deepspeed,
           batch_size, grad_accum, lr, seq_len, epochs, save_steps, save_limit, extra_args):
    """Launch ms-swift SFT training on remote machine."""
    from forge.cli_remote import resolve_machine

    config = ctx.obj["config"]
    backend, inst = resolve_machine(config, machine)

    swift_cmd = (
        f"NPROC_PER_NODE=$(nvidia-smi -L | wc -l) "
        f"swift sft "
        f"--model {model} "
        f"--dataset {data} "
        f"--train_type {train_type} "
        f"--deepspeed {deepspeed} "
        f"--max_length {seq_len} "
        f"--per_device_train_batch_size {batch_size} "
        f"--gradient_accumulation_steps {grad_accum} "
        f"--learning_rate {lr} "
        f"--lr_scheduler_type cosine "
        f"--warmup_ratio 0.03 "
        f"--weight_decay 0.01 "
        f"--max_grad_norm 1.0 "
        f"--num_train_epochs {epochs} "
        f"--bf16 true "
        f"--gradient_checkpointing true "
        f"--save_steps {save_steps} "
        f"--save_total_limit {save_limit} "
        f"--logging_steps 10 "
        f"--output_dir {output} "
        f"--torch_dtype bfloat16"
    )
    if extra_args:
        swift_cmd += f" {extra_args}"

    # Build launch script
    launch_script = (
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        "export CUDA_HOME=/usr/local/cuda\n"
        "export PATH=/usr/local/cuda/bin:$PATH\n"
        "export LD_LIBRARY_PATH=/usr/local/cuda/lib64:${LD_LIBRARY_PATH:-}\n"
        "export TOKENIZERS_PARALLELISM=false\n"
        "export PYTORCH_ALLOC_CONF=expandable_segments:True\n"
        "source /data/venv/bin/activate || source /root/venv/bin/activate\n"
        "source /data/.env 2>/dev/null || source /root/.env 2>/dev/null || true\n"
        f'echo "=== ms-swift training ==="\n'
        f'echo "Date: $(date)"\n'
        f'echo "Data: {data}"\n'
        f'echo "Model: {model}"\n'
        f'echo "Config: {train_type} {deepspeed} batch={batch_size} grad_accum={grad_accum} lr={lr} seq={seq_len}"\n'
        f'echo "========================"\n'
        f"{swift_cmd} 2>&1 | tee /data/logs/train_swift.log\n"
    )

    async def _run():
        # Write launch script
        escaped = launch_script.replace("'", "'\\''")
        await backend.exec(inst, f"mkdir -p /data/logs /data/scripts && echo '{escaped}' > /data/scripts/launch_swift.sh && chmod +x /data/scripts/launch_swift.sh", timeout=10)

        # Clean old checkpoints
        rc, out, _ = await backend.exec(inst, f"rm -rf {output}/checkpoint-* {output}/v1-* 2>/dev/null; echo ok", timeout=30)

        # Launch in screen
        await backend.exec(inst, "screen -dmS train bash /data/scripts/launch_swift.sh", timeout=10)
        click.echo(f"Training launched on {machine}!")
        click.echo(f"  Data: {data}")
        click.echo(f"  Config: {train_type} | {deepspeed} | batch={batch_size}×{grad_accum} | lr={lr} | seq={seq_len}")
        click.echo(f"  Monitor: forge train monitor -m {machine}")
        click.echo(f"  Stop:    forge train stop -m {machine}")

    run_async(_run())


# ===== Monitor Training =====

@train.command()
@click.option("-m", "--machine", required=True, help="Machine name")
@click.option("--log", default=None, help="Log file path (auto-detect if not set)")
@click.pass_context
def monitor(ctx, machine, log):
    """Monitor running training: loss, speed, GPU, checkpoints."""
    from forge.cli_remote import resolve_machine

    config = ctx.obj["config"]
    backend, inst = resolve_machine(config, machine)

    async def _run():
        # Auto-detect log file
        log_path = log
        if not log_path:
            rc, out, _ = await backend.exec(inst,
                "ls -t /data/logs/train_*.log 2>/dev/null | head -1", timeout=10)
            log_path = out.strip() if out.strip() else "/data/logs/train_swift.log"
            click.echo(f"Log: {log_path}")

        # Training metrics
        rc, out, _ = await backend.exec(inst,
            f"grep \"'loss'\" {log_path} | tail -5", timeout=60)
        if out.strip():
            click.echo("=== Recent Training Metrics ===")
            # Parse ms-swift log format
            for line in out.strip().split("\n"):
                if "'loss'" in line:
                    try:
                        # Extract dict from log line
                        start = line.index("{")
                        d = eval(line[start:])
                        step = d.get('global_step/max_steps', '?')
                        loss = d.get('loss', '?')
                        acc = d.get('token_acc', '?')
                        mem = d.get('memory(GiB)', '?')
                        speed = d.get('train_speed(s/it)', '?')
                        remaining = d.get('remaining_time', '?')
                        lr_val = d.get('learning_rate', '?')
                        click.echo(f"  Step {step}  loss={loss:.4f}  acc={acc:.3f}  "
                                   f"mem={mem}GB  {speed:.1f}s/step  ETA={remaining}  lr={lr_val}")
                    except Exception:
                        click.echo(f"  {line.strip()[:120]}")
        else:
            click.echo("No training metrics found (training may not have started yet)")

        # GPU status
        rc, out, _ = await backend.exec(inst,
            "nvidia-smi --query-gpu=index,memory.used,memory.total,utilization.gpu --format=csv,noheader", timeout=10)
        if out.strip():
            click.echo("\n=== GPU Status ===")
            for line in out.strip().split("\n"):
                click.echo(f"  {line.strip()}")

        # Checkpoints
        rc, out, _ = await backend.exec(inst,
            "ls -dt /root/checkpoints/checkpoint-* /root/checkpoints/v1-* 2>/dev/null | head -5", timeout=10)
        if out.strip():
            click.echo("\n=== Checkpoints ===")
            for line in out.strip().split("\n"):
                click.echo(f"  {line.strip()}")

        # Disk
        rc, out, _ = await backend.exec(inst, "df -h / | tail -1", timeout=10)
        if out.strip():
            click.echo(f"\n=== Disk: {out.strip()} ===")

        # Screen
        rc, out, _ = await backend.exec(inst, "screen -ls 2>/dev/null | grep train || echo 'no train screen'", timeout=10)
        click.echo(f"Screen: {out.strip()}")

    run_async(_run())


# ===== Stop Training =====

@train.command()
@click.option("-m", "--machine", required=True, help="Machine name")
@click.option("--force", is_flag=True, help="Force kill without confirmation")
@click.pass_context
def stop(ctx, machine, force):
    """Stop training on remote machine."""
    from forge.cli_remote import resolve_machine

    config = ctx.obj["config"]
    backend, inst = resolve_machine(config, machine)

    if not force:
        click.confirm(f"Stop training on {machine}?", abort=True)

    async def _run():
        await backend.exec(inst, "screen -S train -X quit 2>/dev/null", timeout=10)
        await backend.exec(inst, "pkill -f swift 2>/dev/null; pkill -f train_full_sft 2>/dev/null", timeout=10)
        rc, out, _ = await backend.exec(inst, "ps aux | grep -E 'swift|train_full' | grep -v grep | wc -l", timeout=10)
        remaining = out.strip()
        if remaining == "0":
            click.echo(f"Training stopped on {machine}.")
        else:
            click.echo(f"Warning: {remaining} processes still running. Use --force or manual kill.")

    run_async(_run())
