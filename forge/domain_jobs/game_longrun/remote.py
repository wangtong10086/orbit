"""Remote-machine CLI for the GAME long-running job."""

from __future__ import annotations

import json
import shlex

import click

from forge.domain_jobs.game_longrun.service import default_longrun_root
from forge.remote_ops.service import get_rental, run_async

REMOTE_PROJECT_ROOT = "/root/affine-swarm"


def _machine_selector(ctx) -> str | None:
    current = ctx.parent
    while current is not None:
        if "machine" in current.params:
            return current.params.get("machine")
        current = current.parent
    return None


def _remote_root(job_name: str) -> str:
    return f"{REMOTE_PROJECT_ROOT}/artifacts/game_longrun/{job_name}"


def _launch_env(*, config, job_name: str, repo: str, perfect_target: int, imperfect_target: int, perfect_chunk: int, imperfect_chunk: int, episodes: int, simulations: int, epochs: int, batch_size: int, autotune_batch: bool, device: str, teacher_gate_games: int, teacher_min_win_rate: float, required_streak: int, quick_gate_interval: int, teacher_gate_interval: int, sync_interval: int, max_rounds: int) -> dict[str, str]:
    return {
        "AFFINE_GAME_LONGRUN_JOB_NAME": job_name,
        "AFFINE_GAME_LONGRUN_ROOT": _remote_root(job_name),
        "AFFINE_GAME_POLICY_REPO": repo,
        "AFFINE_GAME_LONGRUN_PERFECT_TARGET": str(perfect_target),
        "AFFINE_GAME_LONGRUN_IMPERFECT_TARGET": str(imperfect_target),
        "AFFINE_GAME_LONGRUN_PERFECT_CHUNK": str(perfect_chunk),
        "AFFINE_GAME_LONGRUN_IMPERFECT_CHUNK": str(imperfect_chunk),
        "AFFINE_GAME_LONGRUN_SELFPLAY_EPISODES": str(episodes),
        "AFFINE_GAME_LONGRUN_SELFPLAY_SIMULATIONS": str(simulations),
        "AFFINE_GAME_LONGRUN_SELFPLAY_EPOCHS": str(epochs),
        "AFFINE_GAME_LONGRUN_BATCH_SIZE": str(batch_size),
        "AFFINE_GAME_LONGRUN_AUTOTUNE_BATCH": "1" if autotune_batch else "0",
        "AFFINE_GAME_LONGRUN_DEVICE": device,
        "AFFINE_GAME_LONGRUN_TEACHER_GAMES": str(teacher_gate_games),
        "AFFINE_GAME_LONGRUN_TEACHER_MIN_WIN_RATE": str(teacher_min_win_rate),
        "AFFINE_GAME_LONGRUN_REQUIRED_STREAK": str(required_streak),
        "AFFINE_GAME_LONGRUN_QUICK_GATE_INTERVAL": str(quick_gate_interval),
        "AFFINE_GAME_LONGRUN_TEACHER_GATE_INTERVAL": str(teacher_gate_interval),
        "AFFINE_GAME_LONGRUN_SYNC_INTERVAL": str(sync_interval),
        "AFFINE_GAME_LONGRUN_MAX_ROUNDS": str(max_rounds),
        "HF_TOKEN": config.hf_token or "",
    }


def _format_exports(env: dict[str, str]) -> str:
    return " && ".join(f"export {name}={shlex.quote(value)}" for name, value in env.items())


async def launch_game_longrun_job(*, backend, inst, env: dict[str, str], job_name: str) -> dict[str, str]:
    log_path = f"/root/logs/{job_name}.log"
    session = job_name
    remote_root = env["AFFINE_GAME_LONGRUN_ROOT"]
    exports = _format_exports(env)
    command = (
        f"mkdir -p {shlex.quote(REMOTE_PROJECT_ROOT)} /root/logs {shlex.quote(remote_root)}"
        f" && screen -S {shlex.quote(session)} -X quit 2>/dev/null || true"
        f" && cd {shlex.quote(REMOTE_PROJECT_ROOT)}"
        f" && export PYTHONPATH={shlex.quote(REMOTE_PROJECT_ROOT)}"
        f" && export PYTHONUNBUFFERED=1"
        f" && {exports}"
        f" && screen -dmS {shlex.quote(session)} bash -lc "
        f"{shlex.quote(f'{REMOTE_PROJECT_ROOT}/.venv/bin/python -u scripts/game/game_longrun_job.py > {log_path} 2>&1')}"
        f" && printf 'SESSION {session}\\nLOG {log_path}\\nROOT {remote_root}\\n'"
    )
    rc, stdout, stderr = await backend.exec(inst, command, timeout=30)
    if rc != 0:
        raise click.ClickException(stderr.strip() or stdout.strip() or "failed to launch GAME long-run job")
    return {"stdout": stdout.strip(), "log_path": log_path, "root_dir": remote_root, "session": session}


async def read_game_longrun_status(*, backend, inst, job_name: str) -> dict[str, object]:
    remote_root = _remote_root(job_name)
    session = job_name
    command = (
        f"STATE={shlex.quote(remote_root + '/state.json')}; "
        f"screen -ls 2>/dev/null | grep -q {shlex.quote(session)} && echo ACTIVE || echo INACTIVE; "
        f"if [ -f \"$STATE\" ]; then cat \"$STATE\"; fi"
    )
    rc, stdout, stderr = await backend.exec(inst, command, timeout=20)
    if rc != 0:
        raise click.ClickException(stderr.strip() or "failed to read GAME long-run job state")
    lines = [line for line in stdout.splitlines() if line.strip() and not line.startswith("Connecting to container ")]
    screen_active = False
    if lines and lines[0] in {"ACTIVE", "INACTIVE"}:
        screen_active = lines[0] == "ACTIVE"
        lines = lines[1:]
    state_payload: dict[str, object] = {}
    if lines:
        try:
            state_payload = json.loads("\n".join(lines))
        except json.JSONDecodeError:
            state_payload = {}
    return {"job_name": job_name, "screen_active": screen_active, "state": state_payload}


async def stop_game_longrun_job(*, backend, inst, job_name: str) -> str:
    remote_root = _remote_root(job_name)
    session = job_name
    command = (
        f"mkdir -p {shlex.quote(remote_root)}"
        f" && printf 'stop\\n' > {shlex.quote(remote_root + '/STOP')}"
        f" && screen -S {shlex.quote(session)} -X quit 2>/dev/null || true"
        f" && echo STOPPED"
    )
    rc, stdout, stderr = await backend.exec(inst, command, timeout=20)
    if rc != 0:
        raise click.ClickException(stderr.strip() or "failed to stop GAME long-run job")
    return stdout.strip()


@click.group(name="game-longrun")
@click.pass_context
def game_longrun(ctx):
    """Remote orchestration for the GAME long-running job."""
    ctx.ensure_object(dict)


@game_longrun.command(name="launch")
@click.option("--job-name", default="game-longrun", help="Remote job name / screen session base")
@click.option("--repo", default="", help="Private HF model repo for self-play checkpoint sync")
@click.option("--perfect-target", default=100000, type=int, help="Target records per perfect-information game")
@click.option("--imperfect-target", default=100000, type=int, help="Target records per imperfect-information game")
@click.option("--perfect-chunk", default=5000, type=int, help="Chunk size for perfect-information collection")
@click.option("--imperfect-chunk", default=5000, type=int, help="Chunk size for imperfect-information collection")
@click.option("--episodes", default=256, type=int, help="Self-play episodes per learner update")
@click.option("--simulations", default=128, type=int, help="Root-search simulations per move")
@click.option("--epochs", default=2, type=int, help="Training epochs per self-play round")
@click.option("--batch-size", default=4096, type=int, help="Training batch size ceiling before autotune")
@click.option("--autotune-batch/--no-autotune-batch", default=True, help="Autotune per-game batch size on the rental")
@click.option("--device", default="", help="Torch device override on rental")
@click.option("--teacher-gate-games", default=200, type=int, help="Teacher arena games")
@click.option("--teacher-min-win-rate", default=0.90, type=float, help="Stop criterion: minimum teacher win rate")
@click.option("--required-streak", default=1, type=int, help="Required consecutive teacher-gate passes")
@click.option("--quick-gate-interval", default=3, type=int, help="Learner updates between quick gates")
@click.option("--teacher-gate-interval", default=5, type=int, help="Learner updates between teacher gates")
@click.option("--sync-interval", default=10, type=int, help="Learner updates between HF syncs")
@click.option("--max-rounds", default=200, type=int, help="Maximum self-play rounds per imperfect-information game")
@click.option("--dry-run", is_flag=True, help="Print the remote launch plan without starting the job")
@click.pass_context
def launch(ctx, job_name, repo, perfect_target, imperfect_target, perfect_chunk, imperfect_chunk, episodes, simulations, epochs, batch_size, autotune_batch, device, teacher_gate_games, teacher_min_win_rate, required_streak, quick_gate_interval, teacher_gate_interval, sync_interval, max_rounds, dry_run):
    """Launch the long-running GAME training and collection job on the selected machine."""
    config = ctx.obj["config"]
    backend, inst = get_rental(config, _machine_selector(ctx))
    resolved_repo = repo or config.hf_game_policy_repo
    if not resolved_repo:
        raise click.ClickException("HF_GAME_POLICY_REPO not set")
    env = _launch_env(
        config=config,
        job_name=job_name,
        repo=resolved_repo,
        perfect_target=perfect_target,
        imperfect_target=imperfect_target,
        perfect_chunk=perfect_chunk,
        imperfect_chunk=imperfect_chunk,
        episodes=episodes,
        simulations=simulations,
        epochs=epochs,
        batch_size=batch_size,
        autotune_batch=autotune_batch,
        device=device,
        teacher_gate_games=teacher_gate_games,
        teacher_min_win_rate=teacher_min_win_rate,
        required_streak=required_streak,
        quick_gate_interval=quick_gate_interval,
        teacher_gate_interval=teacher_gate_interval,
        sync_interval=sync_interval,
        max_rounds=max_rounds,
    )
    if dry_run:
        visible_env = {key: value for key, value in env.items() if key != "HF_TOKEN"}
        click.echo(
            json.dumps(
                {
                    "machine": inst.id,
                    "remote_root": env["AFFINE_GAME_LONGRUN_ROOT"],
                    "local_default_root": default_longrun_root(job_name),
                    "env": visible_env,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    result = run_async(launch_game_longrun_job(backend=backend, inst=inst, env=env, job_name=job_name))
    click.echo(result["stdout"])


@game_longrun.command(name="status")
@click.option("--job-name", default="game-longrun", help="Remote job name / screen session base")
@click.pass_context
def status(ctx, job_name):
    """Read the remote state for the long-running GAME job."""
    config = ctx.obj["config"]
    backend, inst = get_rental(config, _machine_selector(ctx))
    payload = run_async(read_game_longrun_status(backend=backend, inst=inst, job_name=job_name))
    click.echo(json.dumps(payload, indent=2, ensure_ascii=False))


@game_longrun.command(name="stop")
@click.option("--job-name", default="game-longrun", help="Remote job name / screen session base")
@click.pass_context
def stop(ctx, job_name):
    """Request stop for the long-running GAME job and terminate its screen session."""
    config = ctx.obj["config"]
    backend, inst = get_rental(config, _machine_selector(ctx))
    click.echo(run_async(stop_game_longrun_job(backend=backend, inst=inst, job_name=job_name)))
