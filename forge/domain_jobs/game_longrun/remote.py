"""Remote GAME long-run helpers and CLI bridge."""

from __future__ import annotations

import json
import os

import click

from forge.config import ForgeConfig
from forge.remote_ops.service import get_rental, run_async


async def launch_game_longrun_job(**kwargs):
    raise NotImplementedError("launch_game_longrun_job is not implemented in this trimmed checkout")


async def read_game_longrun_status(**kwargs):
    raise NotImplementedError("read_game_longrun_status is not implemented in this trimmed checkout")


async def stop_game_longrun_job(**kwargs):
    raise NotImplementedError("stop_game_longrun_job is not implemented in this trimmed checkout")


def _longrun_env(config: ForgeConfig, episodes: int) -> dict[str, str]:
    repo_id = config.hf_game_policy_repo or os.environ.get("HF_GAME_POLICY_REPO", "")
    if not repo_id:
        raise click.ClickException("HF_GAME_POLICY_REPO not set")
    return {
        "AFFINE_GAME_POLICY_REPO": repo_id,
        "AFFINE_GAME_LONGRUN_SELFPLAY_EPISODES": str(episodes),
        "AFFINE_GAME_LONGRUN_AUTOTUNE_BATCH": "1",
        "AFFINE_GAME_LONGRUN_QUICK_GATE_INTERVAL": "3",
        "AFFINE_GAME_LONGRUN_TEACHER_GATE_INTERVAL": "5",
        "AFFINE_GAME_LONGRUN_SYNC_INTERVAL": "10",
    }


@click.group(name="game-longrun")
def game_longrun():
    """GAME long-run sidecar commands."""


@game_longrun.command(name="launch")
@click.option("--job-name", default="game-longrun")
@click.option("--episodes", default=128, type=int)
@click.pass_context
def launch(ctx, job_name, episodes):
    config = ctx.obj["config"]
    backend, inst = get_rental(config, ctx.obj.get("machine_selector"))
    env = _longrun_env(config, episodes)
    result = run_async(launch_game_longrun_job(backend=backend, instance=inst, job_name=job_name, env=env))
    click.echo(result.get("stdout", "") if isinstance(result, dict) else str(result))


@game_longrun.command(name="status")
@click.option("--job-name", required=True)
@click.pass_context
def status(ctx, job_name):
    config = ctx.obj["config"]
    backend, inst = get_rental(config, ctx.obj.get("machine_selector"))
    payload = run_async(read_game_longrun_status(backend=backend, instance=inst, job_name=job_name))
    click.echo(json.dumps(payload, indent=2, ensure_ascii=False))


@game_longrun.command(name="stop")
@click.option("--job-name", required=True)
@click.pass_context
def stop(ctx, job_name):
    config = ctx.obj["config"]
    backend, inst = get_rental(config, ctx.obj.get("machine_selector"))
    payload = run_async(stop_game_longrun_job(backend=backend, instance=inst, job_name=job_name))
    click.echo(payload)
