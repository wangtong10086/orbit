"""CLI game subcommands — GAME data generation, collection, and bot testing."""

import asyncio
import json
import os
import click


def run_async(coro):
    return asyncio.run(coro)


_ALL_GAMES = ["goofspiel", "leduc_poker", "liars_dice", "gin_rummy", "othello", "hex", "clobber"]
_SCRIPTS = [
    "scripts/game/generate_v11.py",
    "scripts/game/orchestrate_v11.sh",
    "scripts/game/mcts_helper.py",
    "scripts/game/goofspiel_bot.py",
    "scripts/game/leduc_poker_bot.py",
    "scripts/game/gin_rummy_bot.py",
]


def _get_backend(config, machine):
    from forge.cli_remote import resolve_machine
    return resolve_machine(config, machine)


def _remote_base(machine):
    """Get project base path for a machine."""
    # c1 uses ubuntu user with /home/ubuntu/project
    if machine == "c1":
        return "/home/ubuntu/project"
    return "/root/project"


def _upload_scripts(backend, inst, machine):
    """Upload game generation scripts to remote machine."""
    base = _remote_base(machine)
    click.echo(f"Uploading scripts to {machine}...")

    async def _do():
        await backend.exec(inst,
            f"mkdir -p {base}/scripts/game {base}/data/v11 /tmp/v11_logs",
            timeout=30)
        for f in _SCRIPTS:
            await backend.upload(inst, f, f"{base}/{f}")
        await backend.exec(inst,
            f"rm -rf {base}/scripts/game/__pycache__", timeout=10)

    run_async(_do())


@click.group()
@click.pass_context
def game(ctx):
    """GAME data generation and bot testing.

    \b
    forge data game gen clobber -n 1000 -m m1       # Generate on remote
    forge data game gen --all -n 500 -m m1           # All 7 games
    forge data game deploy m1 m2 c1                  # Deploy + start orchestrator
    forge data game collect                          # Collect from all machines
    forge data game progress                         # Check progress
    forge data game kill                             # Kill all workers
    """
    ctx.ensure_object(dict)


@game.command("gen")
@click.argument("game_name", required=False)
@click.option("-n", default=2000, help="Number of entries to generate")
@click.option("-m", "--machine", required=True, help="Machine to run on (m1/m2/c1)")
@click.option("--workers", default=100, help="Number of parallel workers")
@click.option("--all", "all_games", is_flag=True, help="Generate all 7 games")
@click.pass_context
def gen(ctx, game_name, n, machine, workers, all_games):
    """Generate GAME data on remote CPU machine using generate_v11.py.

    \b
    forge data game gen clobber -n 5000 -m m1
    forge data game gen hex -n 2000 -m m2 --workers 50
    forge data game gen --all -n 500 -m c1
    """
    config = ctx.obj["config"]
    backend, inst = _get_backend(config, machine)
    gen_games = _ALL_GAMES if all_games else ([game_name] if game_name else [])
    if not gen_games:
        raise click.UsageError("Specify game name or --all")

    _upload_scripts(backend, inst, machine)
    base = _remote_base(machine)

    async def _run():
        for g in gen_games:
            for w in range(workers):
                seed = (w * 10000 + hash(g) % 100000) & 0x7FFFFFFF
                out_path = f"{base}/data/v11/v11_{g}_{machine}_w{w}.jsonl"
                log_path = f"/tmp/v11_logs/{g}_{machine}_w{w}.log"
                cmd = (
                    f"cd {base} && "
                    f"PYTHONPATH={base}/scripts/game "
                    f"OPENSPIEL_DIR=/root/affinetes/environments/openspiel "
                    f"nohup python3 {base}/scripts/game/generate_v11.py "
                    f"--game {g} -n {n // workers + 1} --start-seed {seed} "
                    f"-o {out_path} > {log_path} 2>&1 &"
                )
                await backend.exec(inst, cmd, timeout=10)
            click.echo(f"  {g}: {workers} workers started on {machine} (target: {n})")

    run_async(_run())


@game.command("deploy")
@click.argument("machines", nargs=-1, required=True)
@click.option("--workers", default=100, help="Workers per machine")
@click.pass_context
def deploy(ctx, machines, workers):
    """Deploy scripts and start orchestrator on machines.

    \b
    forge data game-deploy m1 m2 c1
    forge data game-deploy m1 --workers 80
    """
    config = ctx.obj["config"]

    for machine in machines:
        backend, inst = _get_backend(config, machine)
        _upload_scripts(backend, inst, machine)
        base = _remote_base(machine)

        async def _start(b=backend, i=inst, m=machine, bs=base):
            # Kill existing
            await b.exec(i,
                "pkill -f generate_v11 2>/dev/null; pkill -f orchestrate_v11 2>/dev/null",
                timeout=10)
            # Start orchestrator
            await b.exec(i,
                f"cd {bs} && nohup bash scripts/game/orchestrate_v11.sh {m} {workers} "
                f"> /tmp/v11_orchestrator.log 2>&1 & echo 'started'",
                timeout=15)

        run_async(_start())
        click.echo(f"  {machine}: orchestrator started ({workers} workers)")

    click.echo(f"Deployed to {len(machines)} machines.")


@game.command("collect")
@click.option("--sort", "sort_drafts", is_flag=True, default=True, help="Sort into per-game drafts")
@click.pass_context
def collect(ctx, sort_drafts):
    """Collect data from all machines and sort into per-game drafts.

    \b
    forge data game-collect
    """
    import subprocess
    result = subprocess.run(
        ["bash", "scripts/game/collect_v11.sh"],
        capture_output=True, text=True, timeout=300
    )
    click.echo(result.stdout)
    if result.stderr:
        click.echo(result.stderr)

    if sort_drafts:
        _sort_to_drafts()


@game.command("progress")
@click.option("-m", "--machines", default="m1,m2,c1", help="Comma-separated machine list")
@click.pass_context
def progress(ctx, machines):
    """Check data generation progress on all machines.

    \b
    forge data game-progress
    forge data game-progress -m m1,m2
    """
    config = ctx.obj["config"]
    machine_list = [m.strip() for m in machines.split(",")]

    total = 0
    for machine in machine_list:
        try:
            backend, inst = _get_backend(config, machine)
            base = _remote_base(machine)

            async def _check(b=backend, i=inst, bs=base):
                rc, out, _ = await b.exec(i,
                    f"wc -l {bs}/data/v11/v11_*.jsonl 2>/dev/null | tail -1 || echo '0 total'",
                    timeout=15)
                return out.strip() if out else "0 total"

            async def _workers(b=backend, i=inst):
                rc, out, _ = await b.exec(i,
                    "ps aux | grep generate_v11 | grep -v grep | wc -l",
                    timeout=10)
                return out.strip() if out else "0"

            data_out = run_async(_check())
            worker_count = run_async(_workers())

            # Parse count — handle multi-line output with "Connecting..." prefix
            count = 0
            for part in data_out.split("\n"):
                part = part.strip()
                try:
                    count = int(part.split()[0])
                except (ValueError, IndexError):
                    continue

            # Parse worker count similarly
            wc = 0
            for part in worker_count.split("\n"):
                part = part.strip()
                try:
                    wc = int(part)
                    break
                except (ValueError, IndexError):
                    continue

            click.echo(f"  {machine}: {count:,} entries, {wc} workers")
            total += count
        except Exception as e:
            click.echo(f"  {machine}: error ({e})")

    click.echo(f"  Total: {total:,}")


@game.command("kill")
@click.option("-m", "--machines", default="m1,m2,c1", help="Comma-separated machine list")
@click.pass_context
def kill(ctx, machines):
    """Kill all game generation workers on machines.

    \b
    forge data game-kill
    forge data game-kill -m m1,m2
    """
    config = ctx.obj["config"]
    machine_list = [m.strip() for m in machines.split(",")]

    for machine in machine_list:
        try:
            backend, inst = _get_backend(config, machine)

            async def _kill(b=backend, i=inst):
                await b.exec(i,
                    "pkill -f generate_v11 2>/dev/null; pkill -f orchestrate_v11 2>/dev/null",
                    timeout=10)

            run_async(_kill())
            click.echo(f"  {machine}: killed")
        except Exception as e:
            click.echo(f"  {machine}: error ({e})")


# ===== Bot testing (kept from original) =====

@game.command("test")
@click.argument("game_name", required=False)
@click.option("-n", default=3, help="Number of games per test")
@click.option("-m", "--machine", default=None, help="Machine to run on")
@click.option("--all", "all_games", is_flag=True, help="Test all 7 games")
@click.pass_context
def test(ctx, game_name, n, machine, all_games):
    """Test bot vs MCTS on GPU.

    \b
    forge data game-test clobber -m m3
    forge data game-test --all -m m3
    """
    config = ctx.obj["config"]
    backend, inst = _get_backend(config, machine)
    test_games = _ALL_GAMES if all_games else ([game_name] if game_name else [])
    if not test_games:
        raise click.UsageError("Specify game or --all")

    base = _remote_base(machine or "m3")

    async def _run():
        for g in test_games:
            cmd = (
                f"cd {base} && "
                f"PYTHONPATH={base}/scripts:{base}/scripts/game "
                f"OPENSPIEL_DIR=/root/affinetes/environments/openspiel "
                f"nohup python3 scripts/game/test3.py {g} $RANDOM {n} 10 "
                f"> /root/game_test_{g}.txt 2>&1 & echo '{g} started'"
            )
            rc, out, _ = await backend.exec(inst, cmd, timeout=15)
            click.echo(f"  {out.strip()}" if out else f"  {g}: failed")

    run_async(_run())


def _sort_to_drafts():
    """Sort collected data into per-game draft files with dedup."""
    combined = "data/v11/v11_combined.jsonl"
    draft_dir = "data/drafts/v11_raw"
    os.makedirs(draft_dir, exist_ok=True)

    if not os.path.exists(combined):
        click.echo("No combined file to sort.")
        return

    existing = {}
    added = {}
    for g in _ALL_GAMES:
        existing[g] = set()
        added[g] = 0
        path = os.path.join(draft_dir, f"{g}.jsonl")
        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    try:
                        existing[g].add(json.loads(line).get("task_id"))
                    except Exception:
                        pass

    handles = {g: open(os.path.join(draft_dir, f"{g}.jsonl"), "a") for g in _ALL_GAMES}
    with open(combined) as f:
        for line in f:
            try:
                d = json.loads(line)
                g = d.get("game", "")
                if g not in _ALL_GAMES:
                    continue
                tid = d.get("task_id")
                if tid in existing[g]:
                    continue
                existing[g].add(tid)
                handles[g].write(line)
                added[g] += 1
            except Exception:
                pass

    for h in handles.values():
        h.close()

    total = sum(len(existing[g]) for g in _ALL_GAMES)
    new = sum(added.values())
    click.echo(f"Sorted: +{new} new, {total} total in drafts")
