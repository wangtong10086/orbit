"""CLI entry point for Affine Forge."""

import asyncio
import os
import click

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


# ===== Register subcommand groups =====

from forge.cli_data import data
from forge.cli_train import train
from forge.cli_rental import rental

cli.add_command(data)
cli.add_command(train)
cli.add_command(rental)


# ===== Entry Point =====

def main():
    cli(obj={})
