"""Base contracts and shared helpers for GAME trajectory generators."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable
import json
import random
import sys

from pydantic import Field, JsonValue

from forge.foundation.schema import FrozenModel


PROJECT_ROOT = Path(__file__).resolve().parents[3]
GAME_SCRIPTS_DIR = PROJECT_ROOT / "scripts" / "game"
POLICY_ROOT = PROJECT_ROOT / "artifacts" / "game_policies"


def ensure_game_scripts_path() -> None:
    path = str(GAME_SCRIPTS_DIR)
    if path not in sys.path:
        sys.path.insert(0, path)


def count_jsonl_records(path: str | Path) -> int:
    target = Path(path)
    if not target.exists():
        return 0
    with target.open(encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def append_jsonl_record(path: str | Path, record: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def game_seed_rng(game_name: str, start_seed: int) -> random.Random:
    return random.Random(f"{game_name}:{start_seed}")


class GameTrajectoryGeneratorReport(FrozenModel):
    game: str
    generator_name: str
    generator_family: str
    output: str
    records: int = 0
    wins: int = 0
    attempts: int = 0
    mode: str = "collect"


class PolicyBuildReport(FrozenModel):
    game: str
    generator_name: str
    generator_family: str
    output: str
    iterations: int = 0
    params: dict[str, JsonValue] = Field(default_factory=dict)
    transformed_to_turn_based: bool = False


class PolicyStatusEntry(FrozenModel):
    game: str
    generator_name: str
    generator_family: str
    policy_path: str = ""
    exists: bool = False
    reason: str = ""


@runtime_checkable
class GameTrajectoryGenerator(Protocol):
    def generate_batch(
        self,
        *,
        game_name: str,
        output_path: str,
        sample_count: int,
        start_seed: int,
        attempt_multiplier: int = 4,
    ) -> GameTrajectoryGeneratorReport: ...
