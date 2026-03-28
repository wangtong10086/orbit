"""GAME domain-job commands."""

import os
import click

from forge.remote_ops.service import get_rental, run_async

_REMOTE_BASE = "/root/project"
_ALL_GAMES = ["goofspiel", "leduc_poker", "liars_dice", "gin_rummy", "othello", "hex", "clobber"]


def _sync_scripts(backend, inst):
    """Sync local scripts/ to GPU."""

    click.echo("Syncing scripts...")

    async def _do():
        await backend.exec(inst, f"mkdir -p {_REMOTE_BASE}", timeout=30)
        await backend.upload(inst, "scripts/", f"{_REMOTE_BASE}/")

    run_async(_do())


@click.group()
@click.pass_context
def game(ctx):
    """GAME bot testing and data generation (domain_jobs sidecar)."""
    ctx.ensure_object(dict)


@game.command()
@click.argument("game_name", required=False)
@click.option("-n", default=3, help="Number of games per test")
@click.option("-c", "--concurrency", default=10, help="Max parallel games")
@click.option("--all", "all_games", is_flag=True, help="Test all 7 games")
@click.pass_context
def test(ctx, game_name, n, concurrency, all_games):
    """Test bot vs MCTS on GPU. Auto-syncs scripts."""
    config = ctx.obj["config"]
    backend, inst = get_rental(config, ctx.parent.parent.params.get("machine"))
    test_games = _ALL_GAMES if all_games else ([game_name] if game_name else [])
    if not test_games:
        raise click.UsageError("Specify game or --all")

    _sync_scripts(backend, inst)

    async def _run():
        for g in test_games:
            cmd = (
                f"cd {_REMOTE_BASE} && "
                f"PYTHONPATH={_REMOTE_BASE}/scripts:{_REMOTE_BASE}/scripts/game "
                f"OPENSPIEL_DIR=/root/affinetes/environments/openspiel "
                f"nohup python3 scripts/game/test3.py {g} $RANDOM {n} {concurrency} "
                f"> /root/game_test_{g}.txt 2>&1 & echo '{g} started'"
            )
            _, out, _ = await backend.exec(inst, cmd, timeout=15)
            click.echo(f"  {out.strip()}" if out else f"  {g}: failed")

    run_async(_run())


@game.command()
@click.pass_context
def status(ctx):
    """Check all game test results."""
    config = ctx.obj["config"]
    backend, inst = get_rental(config, ctx.parent.parent.params.get("machine"))

    async def _run():
        games_str = " ".join(_ALL_GAMES)
        _, out, _ = await backend.exec(
            inst,
            f"for g in {games_str}; do r=$(grep '^RESULT' /root/game_test_${{g}}.txt 2>/dev/null); echo \"  $g: ${{r:-running}}\"; done",
            timeout=15,
        )
        click.echo(out.rstrip() if out else "No results")

    run_async(_run())


@game.command()
@click.argument("game_name")
@click.pass_context
def analyze(ctx, game_name):
    """Show full detail for a game test."""
    config = ctx.obj["config"]
    backend, inst = get_rental(config, ctx.parent.parent.params.get("machine"))

    async def _run():
        _, out, _ = await backend.exec(inst, f"cat /root/game_test_{game_name}.txt 2>/dev/null || echo 'No results'", timeout=15)
        click.echo(out.rstrip())

    run_async(_run())


@game.command()
@click.argument("game_name")
@click.option("-n", default=500, help="Number of seeds")
@click.option("--start-seed", default=100000, help="Starting seed")
@click.pass_context
def generate(ctx, game_name, n, start_seed):
    """Generate bot vs MCTS training data on GPU."""
    config = ctx.obj["config"]
    backend, inst = get_rental(config, ctx.parent.parent.params.get("machine"))
    _sync_scripts(backend, inst)

    async def _run():
        out_path = f"/root/game_data_{game_name}.jsonl"
        cmd = (
            f"cd {_REMOTE_BASE} && "
            f"PYTHONPATH={_REMOTE_BASE}/scripts:{_REMOTE_BASE}/scripts/game "
            f"OPENSPIEL_DIR=/root/affinetes/environments/openspiel "
            f"nohup python3 scripts/game/game_bot_gen_mcts.py "
            f"--game {game_name} -n {n} --start-seed {start_seed} "
            f"-o {out_path} "
            f"> /root/game_gen_{game_name}.log 2>&1 & "
            f"echo '{game_name} generating {n} seeds → {out_path}'"
        )
        _, out, _ = await backend.exec(inst, cmd, timeout=15)
        click.echo(out.strip() if out else f"{game_name}: failed to start")

    run_async(_run())


@game.command()
@click.pass_context
def sync(ctx):
    """Sync game scripts to GPU."""
    config = ctx.obj["config"]
    backend, inst = get_rental(config, ctx.parent.parent.params.get("machine"))
    _sync_scripts(backend, inst)
    click.echo("Done.")
