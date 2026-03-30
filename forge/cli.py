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


# Compute commands removed — use `forge rental` for Targon lifecycle,
# `forge remote` for machine operations.


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
from forge.cli_remote import remote
from forge.cli_rental import rental
from forge.cli_game import game

cli.add_command(data)
cli.add_command(train)
cli.add_command(remote)
cli.add_command(rental)

# Game data commands: forge data game gen, forge data game deploy, etc.
data.add_command(game)


# ===== Entry Point =====

def main():
    cli(obj={})
