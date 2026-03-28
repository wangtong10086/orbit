"""Remote-machine CLI family owned by the remote_ops sidecar."""

from __future__ import annotations

import click

from forge.domain_jobs.game import game
from forge.remote_ops.machine_eval import clean_data, eval_pipeline, prepare_data, start_eval, start_sglang
from forge.remote_ops.machine_runtime import (
    kill,
    machine_exec,
    monitor,
    run_cmd,
    start_training,
    status,
    sync_cmd,
    transfer,
    upload_file,
)
from forge.remote_ops.machine_setup import bootstrap, clone_eval, docker_build, setup


@click.group()
@click.option("--machine", "-m", default=None, help="Machine name or index (default: first machine)")
@click.pass_context
def machine(ctx, machine):
    """Remote rental machine management (SSH backend)."""

    ctx.ensure_object(dict)
    ctx.obj["machine_selector"] = machine


for command in [
    status,
    machine_exec,
    kill,
    start_training,
    upload_file,
    transfer,
    start_sglang,
    start_eval,
    monitor,
    setup,
    clone_eval,
    prepare_data,
    eval_pipeline,
    clean_data,
    sync_cmd,
    run_cmd,
    bootstrap,
    docker_build,
]:
    machine.add_command(command)

machine.add_command(game)
