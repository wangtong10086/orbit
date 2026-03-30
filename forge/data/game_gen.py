"""Local GAME data generation helpers."""

from __future__ import annotations

from pathlib import Path

from forge.data.game_trajectory_generators import (
    build_game_trajectory_generator,
    resolve_game_trajectory_generator,
)


SUPPORTED_GAMES = (
    "goofspiel",
    "leduc_poker",
    "liars_dice",
    "gin_rummy",
    "othello",
    "hex",
    "clobber",
)


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


def generate_game_data(
    output_path: str,
    game_name: str | None = None,
    all_games: bool = False,
    sample_count: int = 10,
    start_seed: int = 100000,
    attempt_multiplier: int = 4,
    generator_source: str = "default",
) -> dict:
    """Generate GAME SFT data using the registry-selected generator per game."""

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
    generators: dict[str, str] = {}

    for game in games:
        per_game_output = output if len(games) == 1 else output.with_name(f"{output.stem}_{game}{output.suffix}")
        spec = resolve_game_trajectory_generator(game)
        generator = build_game_trajectory_generator(game, generator_source=generator_source)
        report = generator.generate_batch(
            game_name=game,
            output_path=str(per_game_output),
            sample_count=sample_count,
            start_seed=start_seed,
            attempt_multiplier=attempt_multiplier,
        )
        if report.records == 0:
            raise RuntimeError(
                f"GAME generation produced no records for {game} with generator {spec.name}"
            )

        per_game[game] = report.records
        generators[game] = (
            f"policy_model:{game}_policy_model"
            if generator_source == "policy_model"
            else f"{spec.family}:{spec.name}"
        )
        total_records += report.records
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
        "generators": generators,
        "generator_source": generator_source,
    }
