"""Monitoring CLI family."""

import click

from forge.remote_ops.service import run_async


@click.group()
def monitor():
    """Monitoring sidecar commands."""
    pass


@monitor.command(name="leaderboard")
@click.option("--top", default=50, help="Number of miners to show")
@click.option("--env", default=None, help="Filter by environment")
@click.option("--hotkey", default=None, help="Filter by hotkey prefix")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def leaderboard(ctx, top, env, hotkey, as_json):
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


@monitor.command(name="weaknesses")
@click.option("--top", default=10, help="Number of miners to analyze")
@click.pass_context
def weaknesses(ctx, top):
    """Show the weakest environments across top miners."""
    from forge.monitoring.leaderboard import Leaderboard

    config = ctx.obj["config"]
    lb = Leaderboard(config.api_url)

    async def _run():
        data = await lb.fetch(top=max(top, 10))
        analysis = lb.analyze_weaknesses(data, top=top)
        for env_name, avg in analysis.items():
            click.echo(f"{env_name}: {avg*100:.2f}")

    run_async(_run())
