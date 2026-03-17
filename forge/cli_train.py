"""CLI training subcommands for Affine Forge."""

import asyncio
import os
import click


def run_async(coro):
    """Helper to run async functions from Click commands."""
    return asyncio.run(coro)


@click.group()
def train():
    """Training pipeline commands."""
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
@click.option("--dataset-repo", default=None, help="HF dataset repo (default: HF_DATASET_REPO env var)")
@click.option("--model", default="Qwen/Qwen3-32B", help="Base model")
@click.option("--lr", default=2e-5, type=float, help="Learning rate")
@click.option("--epochs", default=3, type=int, help="Number of epochs")
@click.option("--lora-r", default=16, type=int, help="LoRA rank")
@click.option("--max-seq-len", default=4096, type=int, help="Max sequence length")
@click.option("--batch-size", default=2, type=int, help="Per-device batch size")
@click.option("--grad-accum", default=8, type=int, help="Gradient accumulation steps")
@click.pass_context
def launch(ctx, dataset_file, gpu, hf_repo, dataset_repo, model, lr, epochs,
           lora_r, max_seq_len, batch_size, grad_accum):
    """Launch training from a pre-uploaded HF dataset with custom params."""
    from forge.training.runner import TrainingRunner
    from forge.training.config import TrainConfig

    config = ctx.obj["config"]
    dataset_repo = dataset_repo or os.environ.get("HF_DATASET_REPO", "")
    if not dataset_repo:
        raise click.ClickException("--dataset-repo is required or set HF_DATASET_REPO env var")

    tc = TrainConfig(
        model_name=model,
        learning_rate=lr,
        num_train_epochs=epochs,
        lora_r=lora_r,
        lora_alpha=lora_r * 2,
        max_seq_length=max_seq_len,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=grad_accum,
    )
    if hf_repo:
        tc.hf_backup_repo = hf_repo

    # Parse dataset_file: supports "repo:file" or just "file"
    if ":" in dataset_file and "/" in dataset_file.split(":")[0]:
        dataset_repo, dataset_file = dataset_file.rsplit(":", 1)

    # Derive env name from dataset filename for the runner
    env_name = dataset_file.replace("_sft.jsonl", "").replace(".jsonl", "").replace("/", "-")

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


@train.command(name="dpo-launch")
@click.argument("dataset_file")
@click.option("--gpu", default="H200", help="GPU type")
@click.option("--hf-repo", default=None, help="Target HF repo for checkpoints")
@click.option("--dataset-repo", default=None, help="HF dataset repo (default: HF_DATASET_REPO env var)")
@click.option("--sft-adapter", default="", help="SFT LoRA adapter repo to start from")
@click.option("--model", default="Qwen/Qwen3-32B", help="Base model")
@click.option("--lora-r", default=64, type=int, help="LoRA rank")
@click.option("--max-seq-len", default=4096, type=int, help="Max sequence length")
@click.option("--grad-accum", default=8, type=int, help="Gradient accumulation steps")
@click.pass_context
def dpo_launch(ctx, dataset_file, gpu, hf_repo, dataset_repo, sft_adapter, model,
               lora_r, max_seq_len, grad_accum):
    """Launch DPO training from a pre-uploaded HF dataset."""
    from forge.training.runner import TrainingRunner
    from forge.training.config import TrainConfig

    config = ctx.obj["config"]
    dataset_repo = dataset_repo or os.environ.get("HF_DATASET_REPO", "")
    if not dataset_repo:
        raise click.ClickException("--dataset-repo is required or set HF_DATASET_REPO env var")

    tc = TrainConfig(
        model_name=model,
        lora_r=lora_r,
        lora_alpha=lora_r * 2,
        max_seq_length=max_seq_len,
        gradient_accumulation_steps=grad_accum,
    )
    if hf_repo:
        tc.hf_backup_repo = hf_repo

    runner = TrainingRunner(config)

    async def _run():
        # Generate DPO script instead of SFT
        script = tc.to_dpo_script(f"/root/data/{dataset_file}", sft_adapter=sft_adapter)

        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(script)
            local_script = f.name

        from huggingface_hub import HfApi
        api = HfApi(token=config.hf_token)
        api.upload_file(
            path_or_fileobj=local_script,
            path_in_repo="train_sft.py",  # Same name so container downloads it
            repo_id=dataset_repo,
            repo_type="dataset",
        )
        import os as _os
        _os.unlink(local_script)
        click.echo(f"DPO training script uploaded to {dataset_repo}/train_sft.py")

        env_name = dataset_file.replace("_dpo.jsonl", "").replace(".jsonl", "")
        instance = await runner.launch_on_targon(
            env=f"dpo-{env_name}",
            train_config=tc,
            gpu_type=gpu,
            dataset_hf_repo=dataset_repo,
            dataset_file=dataset_file,
        )
        if instance:
            click.echo(f"\nDPO Container: {instance.id}")

    run_async(_run())


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
