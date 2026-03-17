"""CLI entry point for Affine Forge."""

import asyncio
import os
import click
import sys

from forge.config import ForgeConfig


def run_async(coro):
    """Helper to run async functions from Click commands."""
    return asyncio.run(coro)


@click.group()
@click.pass_context
def cli(ctx):
    """Affine Forge - Leaderboard Training System"""
    ctx.ensure_object(dict)
    ctx.obj["config"] = ForgeConfig.load()


# ===== Leaderboard =====

@cli.command()
@click.option("--top", default=50, help="Number of miners to show")
@click.option("--env", default=None, help="Filter by environment")
@click.option("--hotkey", default=None, help="Filter by hotkey prefix")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def score(ctx, top, env, hotkey, as_json):
    """Show current leaderboard scores."""
    from forge.monitoring.leaderboard import Leaderboard

    config = ctx.obj["config"]
    lb = Leaderboard(config.api_url)

    async def _run():
        data = await lb.fetch(top=256)
        if as_json:
            click.echo(lb.format_json(data, top=top))
        else:
            click.echo(lb.format_table(data, env_filter=env, hotkey_filter=hotkey, top=top))

    run_async(_run())


# ===== Data Commands =====

@cli.group()
def data():
    """Data extraction and management."""
    pass


@data.command()
@click.argument("inputs", nargs=-1, required=True)
@click.option("-o", "--output", required=True, help="Output JSONL path")
@click.option("--max-per-env", default=0, type=int, help="Max records per environment (0=unlimited)")
@click.option("--min-score", default=0.0, type=float, help="Additional score filter")
@click.pass_context
def merge(ctx, inputs, output, max_per_env, min_score):
    """Merge multiple JSONL datasets into one training set.

    Example: forge data merge data/game_sft.jsonl data/lgc-v2_sft.jsonl -o data/mixed_sft.jsonl
    """
    from forge.data.sft import merge_datasets

    result = merge_datasets(
        input_paths=list(inputs),
        output_path=output,
        max_per_env=max_per_env,
        min_score=min_score,
    )
    click.echo(f"\nMerged {result['total']} records -> {output}")
    click.echo("By environment:")
    for env_name, count in result["by_env"].items():
        click.echo(f"  {env_name}: {count}")


@data.command()
@click.argument("path")
@click.pass_context
def analyze(ctx, path):
    """Analyze a JSONL dataset file (score distribution, length, turns, envs)."""
    import json as json_mod
    from forge.data.sft import analyze_dataset

    result = analyze_dataset(path)
    if result["count"] == 0:
        click.echo("Empty dataset")
        return

    click.echo(f"\n=== Dataset Analysis: {path} ===")
    click.echo(f"Total records: {result['count']}")

    s = result["score"]
    click.echo(f"\nScore: min={s['min']:.3f} max={s['max']:.3f} mean={s['mean']:.3f} median={s['median']:.3f}")
    click.echo("  Buckets:")
    for k, v in s["buckets"].items():
        click.echo(f"    {k}: {v} ({v*100/result['count']:.1f}%)")

    c = result["char_length"]
    click.echo(f"\nChar length: min={c['min']} max={c['max']} mean={c['mean']:.0f} median={c['median']}")
    click.echo(f"  Over 16K chars: {c['over_16k']} ({c['over_16k']*100/result['count']:.1f}%)")

    t = result["turns"]
    click.echo(f"\nTurns: min={t['min']} max={t['max']} mean={t['mean']:.1f}")

    click.echo(f"\nEnvironments:")
    for env_name, count in result["envs"].items():
        click.echo(f"  {env_name}: {count}")


@data.command(name="validate")
@click.argument("path")
@click.option("--env", default=None, help="Environment (auto-detected from records if omitted)")
@click.pass_context
def data_validate(ctx, path, env):
    """Deep quality audit of a JSONL dataset (scorer-aligned checks)."""
    import json as json_mod

    with open(path) as f:
        records = [json_mod.loads(line) for line in f]

    if not records:
        click.echo("Empty dataset")
        return

    detected_env = env or records[0].get("env", "")

    if detected_env == "NAVWORLD":
        from forge.data.sft import validate_navworld
        result = validate_navworld(records)
        click.echo(f"\n=== NAVWORLD Validation: {path} ===")
        click.echo(f"Total: {result['total']}  Pass: {result['pass']}  Fail: {result['fail']}  Rate: {result['pass_rate']:.1%}")
        click.echo(f"\nIssues:")
        for issue, count in result["issues"].items():
            click.echo(f"  {issue}: {count} ({count*100/result['total']:.0f}%)")
        click.echo(f"\nTool coverage:")
        for tool, count in sorted(result["tool_coverage"].items(), key=lambda x: -x[1]):
            click.echo(f"  {tool}: {count} ({count*100/result['total']:.0f}%)")
    else:
        # Generic: run through cleaner and report pass/fail
        from forge.data.sft import ENV_CLEANERS
        cleaner = ENV_CLEANERS.get(detected_env)
        if not cleaner:
            click.echo(f"No validator for env '{detected_env}'. Available: {', '.join(ENV_CLEANERS.keys())}")
            return
        passed = sum(1 for r in records if cleaner(dict(r)) is not None)
        click.echo(f"\n=== {detected_env} Validation: {path} ===")
        click.echo(f"Total: {len(records)}  Pass: {passed}  Fail: {len(records)-passed}  Rate: {passed/len(records):.1%}")


@data.command(name="status")
@click.pass_context
def data_status(ctx):
    """Show data inventory: local files, counts, freshness vs synth_config targets."""
    import json as json_mod
    from pathlib import Path

    config = ctx.obj["config"]
    config_path = config.project_root / "forge" / "data" / "synth_config.json"

    if not config_path.exists():
        raise click.ClickException("synth_config.json not found")

    with open(config_path) as f:
        synth = json_mod.load(f)

    click.echo(f"\n{'Environment':12} {'Enabled':>8} {'Priority':>9} {'Current':>8} {'Target':>8} {'File':>8} {'Status'}")
    click.echo("-" * 80)

    for env_name, env_cfg in sorted(synth["environments"].items(), key=lambda x: x[1].get("priority", 99)):
        enabled = "Yes" if env_cfg.get("enabled") else "No"
        priority = env_cfg.get("priority", "—")
        current = env_cfg.get("current_count", 0)
        target = env_cfg.get("target_count", "—")

        # Check local file (try output, synthetic_output, dynamo_output)
        output = env_cfg.get("output") or env_cfg.get("synthetic_output") or env_cfg.get("dynamo_output") or ""
        local_path = config.project_root / output if output else None
        file_count = 0
        if local_path and local_path.exists():
            with open(local_path) as f:
                file_count = sum(1 for _ in f)
            file_str = str(file_count)
        else:
            file_str = "—"

        # Status
        if not env_cfg.get("enabled"):
            status = "disabled"
        elif isinstance(target, int) and current >= target:
            status = "done"
        else:
            status = f"need {target - current}" if isinstance(target, int) else "?"

        click.echo(f"{env_name:12} {enabled:>8} {priority!s:>9} {current:>8} {target!s:>8} {file_str:>8} {status}")

    click.echo(f"Synth status: {synth.get('status', '?')}")


@data.command(name="upload")
@click.argument("path")
@click.option("--filename", default=None, help="Target filename in HF repo (default: same as local)")
@click.option("--repo", default=None, help="HF dataset repo (default: HF_DATASET_REPO env var)")
@click.pass_context
def data_upload(ctx, path, filename, repo):
    """Upload a local JSONL file to HuggingFace dataset repo."""
    from pathlib import Path as P
    from huggingface_hub import HfApi

    config = ctx.obj["config"]
    repo = repo or os.environ.get("HF_DATASET_REPO", "")
    if not repo:
        raise click.ClickException("--repo is required or set HF_DATASET_REPO env var")

    local = P(path)
    if not local.exists():
        raise click.ClickException(f"File not found: {path}")

    target = filename or local.name

    # Count lines
    with open(local) as f:
        count = sum(1 for _ in f)

    click.echo(f"Uploading {local.name} ({count} records) -> {repo}/{target}")
    api = HfApi(token=config.hf_token)
    api.upload_file(
        path_or_fileobj=str(local),
        path_in_repo=target,
        repo_id=repo,
        repo_type="dataset",
    )
    click.echo(f"Done: https://huggingface.co/datasets/{repo}")


@data.command(name="navworld-gen")
@click.option("-n", "--num", default=10, type=int, help="Number of samples to generate")
@click.option("-o", "--output", default="data/navworld_synthetic.jsonl", help="Output path")
@click.option("--model", default="qwen3-max", help="LLM model for generation")
@click.option("--start-id", default=0, type=int, help="Starting task ID")
@click.option("--concurrency", default=3, type=int, help="Parallel requests")
@click.pass_context
def navworld_gen(ctx, num, output, model, start_id, concurrency):
    """Generate synthetic NAVWORLD SFT data using AMap API + LLM."""
    from forge.data.navworld_gen import generate_batch

    amap_key = os.environ.get("AMAP_API_KEY") or os.environ.get("AMAP_MAPS_API_KEY", "")
    api_key = os.environ.get("QWEN_API_KEY") or os.environ.get("CHUTES_API_KEY", "")

    if not amap_key:
        raise click.ClickException("AMAP_API_KEY not set")
    if not api_key:
        raise click.ClickException("QWEN_API_KEY not set")

    click.echo(f"Generating {num} NAVWORLD samples using {model}")
    run_async(generate_batch(
        num_samples=num,
        output_path=output,
        amap_key=amap_key,
        api_key=api_key,
        model=model,
        start_id=start_id,
        concurrency=concurrency,
    ))


# ===== Compute Commands =====

@cli.group()
def compute():
    """GPU compute management."""
    pass


@compute.command()
@click.pass_context
def capacity(ctx):
    """Show available GPU capacity on Targon."""
    from forge.compute.targon import TargonBackend

    config = ctx.obj["config"]
    if not config.targon_api_key:
        click.echo("Error: TARGON_API_KEY not set")
        return

    async def _run():
        backend = TargonBackend(config.targon_api_key)
        caps = await backend.capacity()
        click.echo(f"\n{'Resource':20} {'Available':>10}")
        click.echo("-" * 32)
        for c in caps:
            if c["count"] > 0:
                click.echo(f"{c['name']:20} {c['count']:>10}")

    run_async(_run())


@compute.command(name="list")
@click.pass_context
def list_instances(ctx):
    """List all active compute instances."""
    from forge.compute.manager import ComputeManager

    config = ctx.obj["config"]
    cm = ComputeManager(config)

    async def _run():
        instances = await cm.list_all()
        if not instances:
            click.echo("No active instances")
            return

        click.echo(f"\n{'ID':40} {'Backend':8} {'GPU':8} {'Status':12} {'URL/Host'}")
        click.echo("-" * 100)
        for inst in instances:
            loc = inst.url or inst.host or "-"
            click.echo(f"{inst.id:40} {inst.backend:8} {inst.gpu_type:8} {inst.status:12} {loc}")

    run_async(_run())


@compute.command()
@click.option("--gpu", default="H200", help="GPU type (H100, H200, B200)")
@click.option("--name", default="affine-train", help="Instance name")
@click.pass_context
def provision(ctx, gpu, name):
    """Provision a new Targon GPU container."""
    from forge.compute.targon import TargonBackend

    config = ctx.obj["config"]
    if not config.targon_api_key:
        click.echo("Error: TARGON_API_KEY not set")
        return

    async def _run():
        backend = TargonBackend(config.targon_api_key)
        inst = await backend.provision(gpu_type=gpu, name=name)
        click.echo(f"Provisioned {gpu} instance:")
        click.echo(f"  ID: {inst.id}")
        click.echo(f"  URL: {inst.url}")
        click.echo(f"  Status: {inst.status}")

    run_async(_run())


@compute.command()
@click.argument("instance_id")
@click.pass_context
def terminate(ctx, instance_id):
    """Terminate a Targon container."""
    from forge.compute.targon import TargonBackend

    config = ctx.obj["config"]
    if not config.targon_api_key:
        click.echo("Error: TARGON_API_KEY not set")
        return

    async def _run():
        backend = TargonBackend(config.targon_api_key)
        from forge.compute.base import GpuInstance
        inst = GpuInstance(id=instance_id, backend="targon", gpu_type="unknown", status="running")
        await backend.terminate(inst)
        click.echo(f"Terminated: {instance_id}")

    run_async(_run())


@compute.command()
@click.argument("instance_id")
@click.option("--tail", default=0, type=int, help="Show last N lines (no follow)")
@click.pass_context
def logs(ctx, instance_id, tail):
    """Stream container logs in real time."""
    from forge.compute.targon import TargonBackend

    config = ctx.obj["config"]
    if not config.targon_api_key:
        raise click.ClickException("TARGON_API_KEY not set")

    async def _run():
        backend = TargonBackend(config.targon_api_key)
        if tail:
            lines = await backend.logs_snapshot(instance_id, tail=tail)
            for line in lines:
                click.echo(line)
        else:
            click.echo(f"Streaming logs for {instance_id} (Ctrl+C to stop)...")
            try:
                async for line in backend.logs(instance_id, follow=True):
                    click.echo(line)
            except KeyboardInterrupt:
                pass

    run_async(_run())


# ===== Training Commands =====

@cli.group()
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


# ===== Deploy Commands =====

@cli.group()
def deploy():
    """Model deployment pipeline."""
    pass


@deploy.command()
@click.argument("adapter_source")
@click.option("--deploy-repo", required=True, help="Target HF repo for merged model")
@click.option("--base-model", default="Qwen/Qwen3-32B", help="Base model name")
@click.pass_context
def merge(ctx, adapter_source, deploy_repo, base_model):
    """Merge LoRA adapter and upload to HuggingFace."""
    from forge.deploy import DeployPipeline

    config = ctx.obj["config"]
    dp = DeployPipeline(config)
    revision = dp.merge_and_upload(adapter_source, deploy_repo, base_model)
    click.echo(f"\nRevision: {revision}")


@deploy.command()
@click.argument("hf_repo")
@click.option("--revision", default="main", help="HF repo revision")
@click.pass_context
def chutes_config(ctx, hf_repo, revision):
    """Generate Chutes deployment config."""
    from forge.deploy import DeployPipeline

    config = ctx.obj["config"]
    dp = DeployPipeline(config)
    dp.generate_deploy_script(hf_repo, revision)


@deploy.command(name="plan")
@click.option("--adapter", default="", help="LoRA adapter source HF repo")
@click.option("--deploy-repo", default="", help="Target HF repo for merged model")
@click.option("--base-model", default="Qwen/Qwen3-32B", help="Base model")
@click.pass_context
def deploy_plan(ctx, adapter, deploy_repo, base_model):
    """Show full deployment plan (dry run)."""
    from forge.deploy import DeployPipeline

    config = ctx.obj["config"]
    dp = DeployPipeline(config)
    dp.full_deploy_plan(adapter, deploy_repo, base_model)


# ===== Rental Commands =====

@cli.group()
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


# ===== Entry Point =====

def main():
    cli(obj={})
