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

from forge.cli_control import control
from forge.cli_data import data
from forge.cli_worker import worker
from forge.remote_ops.cli import remote
from forge.monitoring.cli import monitor

cli.add_command(data)
cli.add_command(control)
cli.add_command(worker)
cli.add_command(remote)
cli.add_command(monitor)


# ===== Entry Point =====

def main():
    cli(obj={})
