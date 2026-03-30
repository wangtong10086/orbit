"""Local GAME data generation helpers."""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
from pathlib import Path

from forge.data.game_trajectory_generators import resolve_game_trajectory_generator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SUPPORTED_GAMES = (
    "goofspiel",
    "leduc_poker",
    "liars_dice",
    "gin_rummy",
    "othello",
    "hex",
    "clobber",
)


def require_game_script() -> Path:
    script = Path(resolve_game_trajectory_generator("goofspiel").script_path)
    if not script.exists():
        raise FileNotFoundError(f"GAME generator script not found: {script}")
    return script


def _script_for_game(game_name: str) -> Path:
    spec = resolve_game_trajectory_generator(game_name)
    script = Path(spec.script_path)
    if not script.exists():
        raise FileNotFoundError(f"GAME generator script not found: {script}")
    return script


def require_game_deps() -> None:
    missing = []
    for module_name in ("numpy", "pyspiel"):
        try:
            __import__(module_name)
        except ImportError:
            missing.append(module_name)
    if missing:
        raise RuntimeError(
            "GAME generation requires missing Python packages: "
            + ", ".join(sorted(missing))
        )


def _line_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def generate_game_data(
    output_path: str,
    game_name: str | None = None,
    all_games: bool = False,
    sample_count: int = 10,
    start_seed: int = 100000,
    attempt_multiplier: int = 4,
) -> dict:
    """Generate GAME SFT data by oversampling seeds until enough wins are kept."""

    require_game_script()
    require_game_deps()

    if all_games:
        games = list(SUPPORTED_GAMES)
    elif game_name:
        games = [game_name]
    else:
        raise ValueError("Specify game_name or all_games=True")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("", encoding="utf-8")

    total_records = 0
    per_game: dict[str, int] = {}
    for game in games:
        per_game_output = output if len(games) == 1 else output.with_name(f"{output.stem}_{game}{output.suffix}")
        per_game_output.write_text("", encoding="utf-8")
        target = sample_count
        attempts = 0
        max_attempts = max(sample_count * attempt_multiplier, sample_count)
        seed_rng = random.Random(f"{game}:{start_seed}")
        generator_spec = resolve_game_trajectory_generator(game)

        while _line_count(per_game_output) < target and attempts < max_attempts:
            batch = max(1, min(target - _line_count(per_game_output), 20))
            batch_seed = seed_rng.randint(0, max(1, 2**31 - batch - 1))
            cmd = [
                sys.executable,
                str(generator_spec.script_path),
                "--game",
                game,
                "-n",
                str(batch),
                "--start-seed",
                str(batch_seed),
                "-o",
                str(per_game_output),
            ]
            env = os.environ.copy()
            env.update(generator_spec.env)
            result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, env=env)
            if result.stdout:
                print(result.stdout.rstrip())
            if result.stderr:
                print(result.stderr.rstrip())
            if result.returncode != 0:
                raise RuntimeError(f"GAME generation failed for {game}")
            attempts += batch
            if _line_count(per_game_output) == 0 and attempts >= max_attempts:
                break

        produced = _line_count(per_game_output)
        if produced == 0:
            raise RuntimeError(
                f"GAME generation produced no records for {game} after {attempts} attempts"
            )

        per_game[game] = produced
        total_records += produced
        if per_game_output != output:
            with per_game_output.open(encoding="utf-8") as src, output.open("a", encoding="utf-8") as dst:
                for line in src:
                    if line.strip():
                        dst.write(line)

    return {
        "output": str(output),
        "records": total_records,
        "per_game": per_game,
        "target_per_game": sample_count,
    }
