"""Experiment CLI family."""

import json
import click

from forge.pipeline.experiment import ExperimentTracker


@click.group()
@click.option("--dir", "experiments_dir", default="experiments", help="Experiments directory")
@click.pass_context
def exp(ctx, experiments_dir):
    """Experiment metadata and lifecycle commands."""
    ctx.ensure_object(dict)
    ctx.obj["experiments_dir"] = experiments_dir


@exp.command(name="list")
@click.option("--status", default=None, help="Filter by status")
@click.pass_context
def list_experiments(ctx, status):
    """List experiments."""
    tracker = ExperimentTracker(ctx.obj["experiments_dir"])
    experiments = tracker.list_experiments(status=status)
    for exp_item in experiments:
        click.echo(f"{exp_item.id}\t{exp_item.status}\t{exp_item.variable}")


@exp.command(name="show")
@click.argument("exp_id")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def show_experiment(ctx, exp_id, as_json):
    """Show one experiment."""
    tracker = ExperimentTracker(ctx.obj["experiments_dir"])
    experiment = tracker.load(exp_id)
    if experiment is None:
        raise click.ClickException(f"Experiment not found: {exp_id}")
    if as_json:
        click.echo(json.dumps(experiment.to_dict(), indent=2))
    else:
        click.echo(f"id: {experiment.id}")
        click.echo(f"status: {experiment.status}")
        click.echo(f"variable: {experiment.variable}")
        click.echo(f"hypothesis: {experiment.hypothesis}")


@exp.command(name="set-status")
@click.argument("exp_id")
@click.argument("status")
@click.pass_context
def set_status(ctx, exp_id, status):
    """Update experiment status."""
    tracker = ExperimentTracker(ctx.obj["experiments_dir"])
    if not tracker.update_status(exp_id, status):
        raise click.ClickException(f"Experiment not found: {exp_id}")
    click.echo(f"{exp_id} -> {status}")
