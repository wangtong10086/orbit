"""CLI entry point for Affine Forge."""

import click

from forge.config import ForgeConfig


@click.group()
@click.pass_context
def cli(ctx):
    """Affine Forge - Leaderboard Training System"""
    ctx.ensure_object(dict)
    ctx.obj["config"] = ForgeConfig.load()


# ===== Register subcommand groups =====

from forge.cli_data import data
from forge.cli_train import train
from forge.cli_eval import eval
from forge.cli_exp import exp
from forge.remote_ops.cli import remote
from forge.monitoring.cli import monitor

cli.add_command(data)
cli.add_command(train)
cli.add_command(eval)
cli.add_command(exp)
cli.add_command(remote)
cli.add_command(monitor)


# ===== Entry Point =====

def main():
    cli(obj={})
