"""CLI training subcommands for Affine Forge (ms-swift based)."""

import asyncio
import os
import click


def run_async(coro):
    """Helper to run async functions from Click commands."""
    return asyncio.run(coro)


@click.group()
def train():
    """Training pipeline commands (ms-swift)."""
    pass


@train.command()
@click.argument("env")
@click.option("--gpu", default="H200", help="GPU type")
@click.option("--min-score", default=0.5, type=float, help="Min score for data")
@click.option("--backend", default="targon", type=click.Choice(["targon", "ssh"]), help="Compute backend")
@click.option("--max-samples", default=0, type=int, help="Max training samples")
@click.pass_context
def full(ctx, env, gpu, min_score, backend, max_samples):
    """Full pipeline: extract data -> train model."""
    from forge.training.runner import TrainingRunner

    config = ctx.obj["config"]
    runner = TrainingRunner(config)

    run_async(runner.full_pipeline(
        env=env,
        gpu_type=gpu,
        min_score=min_score,
        backend=backend,
        max_samples=max_samples,
    ))


@train.command()
@click.argument("env")
@click.option("--min-score", default=0.5, type=float)
@click.option("-o", "--output", default=None)
@click.option("--max-samples", default=0, type=int)
@click.pass_context
def prepare(ctx, env, min_score, output, max_samples):
    """Prepare SFT dataset (extract only, no training)."""
    from forge.training.runner import TrainingRunner

    config = ctx.obj["config"]
    runner = TrainingRunner(config)

    run_async(runner.prepare_dataset(env, min_score=min_score, output=output, max_samples=max_samples))


@train.command()
@click.argument("env")
@click.pass_context
def plan(ctx, env):
    """Show training plan for an environment."""
    click.echo(f"\n=== Training Plan for {env} ===\n")
    click.echo(f"1. Extract data:    forge data extract {env} --min-score 0.5")
    click.echo(f"2. Check capacity:  forge compute capacity")
    click.echo(f"3. Full pipeline:   forge train full {env} --gpu H200")
    click.echo(f"4. Monitor:         forge compute list")
    click.echo(f"5. Check scores:    forge score --env {env}")
    click.echo()


@train.command()
@click.argument("dataset_file")
@click.option("--gpu", default="H200", help="GPU type")
@click.option("--hf-repo", default=None, help="Target HF repo for checkpoints")
@click.option("--dataset-repo", default=None, help="HF dataset repo")
@click.option("--model", default="Qwen/Qwen3-32B", help="Base model")
@click.option("--train-type", default="sft", type=click.Choice(["sft", "rlhf", "pt"]),
              help="Training type")
@click.option("--rlhf-type", default="dpo",
              type=click.Choice(["dpo", "grpo", "kto", "cpo", "simpo", "orpo", "ppo"]),
              help="RLHF algorithm (when --train-type=rlhf)")
@click.option("--tuner-type", default="lora", type=click.Choice(["lora", "full"]),
              help="Tuner type (lora or full parameter)")
@click.option("--lr", default=1e-4, type=float, help="Learning rate")
@click.option("--epochs", default=1, type=int, help="Number of epochs")
@click.option("--lora-r", default=64, type=int, help="LoRA rank")
@click.option("--max-length", default=4096, type=int, help="Max sequence length")
@click.option("--batch-size", default=2, type=int, help="Per-device batch size")
@click.option("--grad-accum", default=8, type=int, help="Gradient accumulation steps")
@click.option("--deepspeed", default=None, help="DeepSpeed config (zero2, zero3, etc.)")
@click.option("--no-quant", is_flag=True, help="Disable QLoRA quantization")
@click.option("--sft-adapter", default=None, help="SFT adapter to init from (for RLHF)")
@click.pass_context
def launch(ctx, dataset_file, gpu, hf_repo, dataset_repo, model, train_type,
           rlhf_type, tuner_type, lr, epochs, lora_r, max_length, batch_size,
           grad_accum, deepspeed, no_quant, sft_adapter):
    """Launch ms-swift training from a pre-uploaded HF dataset.

    Supports SFT, RLHF (DPO/GRPO/KTO/CPO/SimPO/ORPO/PPO),
    with LoRA/QLoRA or full parameter training.

    Examples:

      forge train launch data.jsonl --dataset-repo myrepo --train-type sft

      forge train launch data.jsonl --train-type rlhf --rlhf-type grpo

      forge train launch data.jsonl --tuner-type full --no-quant
    """
    from forge.training.runner import TrainingRunner
    from forge.training.config import SwiftConfig

    config = ctx.obj["config"]
    dataset_repo = dataset_repo or os.environ.get("HF_DATASET_REPO", "")
    if not dataset_repo:
        raise click.ClickException("--dataset-repo is required or set HF_DATASET_REPO env var")

    tc = SwiftConfig(
        model=model,
        train_type=train_type,
        rlhf_type=rlhf_type,
        tuner_type=tuner_type,
        learning_rate=lr,
        num_train_epochs=epochs,
        lora_rank=lora_r,
        lora_alpha=lora_r * 2,
        max_length=max_length,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=grad_accum,
        quant_method=None if no_quant or tuner_type == "full" else "bnb",
        quant_bits=None if no_quant or tuner_type == "full" else 4,
        deepspeed=deepspeed,
    )
    if hf_repo:
        tc.hf_backup_repo = hf_repo
    if sft_adapter:
        tc.adapters = [sft_adapter]
        tc.ref_adapters = [sft_adapter]

    # Parse dataset_file: supports "repo:file" or just "file"
    if ":" in dataset_file and "/" in dataset_file.split(":")[0]:
        dataset_repo, dataset_file = dataset_file.rsplit(":", 1)

    # Derive env name from dataset filename
    env_name = dataset_file.replace("_sft.jsonl", "").replace("_dpo.jsonl", "").replace(".jsonl", "").replace("/", "-")

    # Validate config
    from forge.training.sft import SwiftBackend
    backend = SwiftBackend()
    issues = backend.validate_config(tc)
    if issues:
        for issue in issues:
            click.echo(f"Config error: {issue}", err=True)
        raise click.ClickException("Invalid training configuration")

    runner = TrainingRunner(config)
    instance = run_async(runner.launch_on_targon(
        env=env_name,
        train_config=tc,
        gpu_type=gpu,
        dataset_hf_repo=dataset_repo,
        dataset_file=dataset_file,
    ))
    if instance:
        click.echo(f"\nContainer: {instance.id}")
        click.echo(f"Monitor: python3 -m forge train status")


@train.command(name="rlhf-launch")
@click.argument("dataset_file")
@click.option("--gpu", default="H200", help="GPU type")
@click.option("--hf-repo", default=None, help="Target HF repo for checkpoints")
@click.option("--dataset-repo", default=None, help="HF dataset repo")
@click.option("--rlhf-type", default="dpo",
              type=click.Choice(["dpo", "grpo", "kto", "cpo", "simpo", "orpo", "ppo"]),
              help="RLHF algorithm")
@click.option("--sft-adapter", default="", help="SFT LoRA adapter to init from")
@click.option("--model", default="Qwen/Qwen3-32B", help="Base model")
@click.option("--lora-r", default=64, type=int, help="LoRA rank")
@click.option("--max-length", default=4096, type=int, help="Max sequence length")
@click.option("--grad-accum", default=8, type=int, help="Gradient accumulation steps")
@click.pass_context
def rlhf_launch(ctx, dataset_file, gpu, hf_repo, dataset_repo, rlhf_type,
                sft_adapter, model, lora_r, max_length, grad_accum):
    """Launch RLHF training (DPO/GRPO/KTO/etc.) via ms-swift.

    Shortcut for: forge train launch --train-type rlhf --rlhf-type <type>
    """
    from forge.training.runner import TrainingRunner
    from forge.training.config import SwiftConfig

    config = ctx.obj["config"]
    dataset_repo = dataset_repo or os.environ.get("HF_DATASET_REPO", "")
    if not dataset_repo:
        raise click.ClickException("--dataset-repo is required or set HF_DATASET_REPO env var")

    tc = SwiftConfig(
        model=model,
        train_type="rlhf",
        rlhf_type=rlhf_type,
        lora_rank=lora_r,
        lora_alpha=lora_r * 2,
        max_length=max_length,
        gradient_accumulation_steps=grad_accum,
    )
    if hf_repo:
        tc.hf_backup_repo = hf_repo
    if sft_adapter:
        tc.adapters = [sft_adapter]
        tc.ref_adapters = [sft_adapter]

    env_name = dataset_file.replace("_dpo.jsonl", "").replace(".jsonl", "")

    runner = TrainingRunner(config)
    instance = run_async(runner.launch_on_targon(
        env=f"rlhf-{env_name}",
        train_config=tc,
        gpu_type=gpu,
        dataset_hf_repo=dataset_repo,
        dataset_file=dataset_file,
    ))
    if instance:
        click.echo(f"\n{rlhf_type.upper()} Container: {instance.id}")


# Keep dpo-launch as alias for backward compat
@train.command(name="dpo-launch", hidden=True)
@click.argument("dataset_file")
@click.option("--gpu", default="H200")
@click.option("--hf-repo", default=None)
@click.option("--dataset-repo", default=None)
@click.option("--sft-adapter", default="")
@click.option("--model", default="Qwen/Qwen3-32B")
@click.option("--lora-r", default=64, type=int)
@click.option("--max-seq-len", default=4096, type=int)
@click.option("--grad-accum", default=8, type=int)
@click.pass_context
def dpo_launch(ctx, dataset_file, gpu, hf_repo, dataset_repo, sft_adapter,
               model, lora_r, max_seq_len, grad_accum):
    """Launch DPO training (deprecated: use rlhf-launch --rlhf-type dpo)."""
    ctx.invoke(rlhf_launch, dataset_file=dataset_file, gpu=gpu, hf_repo=hf_repo,
               dataset_repo=dataset_repo, rlhf_type="dpo", sft_adapter=sft_adapter,
               model=model, lora_r=lora_r, max_length=max_seq_len, grad_accum=grad_accum)


@train.command()
@click.option("--tail", default=50, type=int, help="Show last N log lines")
@click.pass_context
def status(ctx, tail):
    """Show training status (download logs and metrics from HuggingFace)."""
    from huggingface_hub import hf_hub_download

    config = ctx.obj["config"]
    repo = config.hf_backup_repo
    if not repo:
        click.echo("Error: HF_BACKUP_REPO not set")
        return

    import json, tempfile

    # 1. Full log file
    try:
        path = hf_hub_download(
            repo_id=repo, filename="training.log",
            repo_type="model", token=config.hf_token,
            cache_dir=tempfile.mkdtemp(),
        )
        with open(path) as f:
            lines = f.readlines()
        click.echo(f"\n=== training.log ({len(lines)} lines, last {tail}) ===")
        for line in lines[-tail:]:
            click.echo(line.rstrip())
    except Exception:
        click.echo("\ntraining.log: not found")

    # 2. Structured metrics
    try:
        path = hf_hub_download(
            repo_id=repo, filename="training_log.json",
            repo_type="model", token=config.hf_token,
            cache_dir=tempfile.mkdtemp(),
        )
        with open(path) as f:
            data = json.load(f)
        click.echo(f"\n=== Metrics (step {data.get('global_step', '?')}, epoch {data.get('epoch', '?')}) ===")
        click.echo(f"Timestamp: {data.get('timestamp', '?')}")
        history = data.get("log_history", [])
        if history:
            click.echo("Recent loss:")
            for entry in history[-5:]:
                loss = entry.get("loss", "")
                step = entry.get("step", "")
                if loss:
                    click.echo(f"  step {step}: loss={loss:.4f}")
    except Exception:
        click.echo("\ntraining_log.json: not found")
