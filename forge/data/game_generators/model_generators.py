"""Trained policy-model GAME trajectory generator."""

from __future__ import annotations

from pathlib import Path

from forge.data.game_generators.base import (
    GameTrajectoryGeneratorReport,
    append_jsonl_record,
    count_jsonl_records,
    ensure_game_scripts_path,
    game_seed_rng,
)
from forge.data.game_policy_models import default_policy_model_dir, policy_model_status
from forge.data.game_policy_models.inference import play_record as selfplay_record, resolve_policy_model_dir


ensure_game_scripts_path()


class PolicyModelTrajectoryGenerator:
    """Sample GAME trajectories from a trained per-game policy model."""

    def __init__(self, *, name: str, family: str, game_params: dict[str, object], model_dir: str = ""):
        self.name = name
        self.family = family
        self.game_params = dict(game_params)
        self.model_dir = model_dir

    def generate_batch(
        self,
        *,
        game_name: str,
        output_path: str,
        sample_count: int,
        start_seed: int,
        attempt_multiplier: int = 4,
    ) -> GameTrajectoryGeneratorReport:
        resolved_model_dir = self.model_dir or default_policy_model_dir(game_name)
        target = Path(resolved_model_dir)
        resolved = Path(resolve_policy_model_dir(str(target)))
        status = policy_model_status(game_name=game_name, model_dir=str(target))
        if not status.exists:
            raise FileNotFoundError(
                f"GAME policy model missing for {game_name}: {target}. "
                f"Run `forge data game-selfplay-train --game {game_name}` first."
            )

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("", encoding="utf-8")

        attempts = 0
        max_attempts = max(sample_count * max(attempt_multiplier, 1), sample_count)
        seed_rng = game_seed_rng(game_name, start_seed)

        while count_jsonl_records(output) < sample_count and attempts < max_attempts:
            seed = seed_rng.randint(0, max(1, 2**31 - 2))
            record = selfplay_record(
                game_name=game_name,
                seed=seed,
                model_dir=str(resolved),
            )
            attempts += 1
            if record:
                append_jsonl_record(output, record)

        wins = count_jsonl_records(output)
        return GameTrajectoryGeneratorReport(
            game=game_name,
            generator_name=self.name,
            generator_family=self.family,
            output=str(output),
            records=wins,
            wins=wins,
            attempts=attempts,
            mode="policy_model",
        )
