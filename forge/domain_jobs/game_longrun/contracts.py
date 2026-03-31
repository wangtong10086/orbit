"""Contracts for the GAME long-running training and collection job."""

from __future__ import annotations

from pydantic import Field

from forge.foundation.schema import FrozenModel

PERFECT_INFO_GAMES = ("othello", "hex", "clobber")
IMPERFECT_INFO_GAMES = ("leduc_poker", "goofspiel", "liars_dice", "gin_rummy")


class GameLongRunConfig(FrozenModel):
    job_name: str = "game-longrun"
    root_dir: str
    perfect_target: int = 100_000
    imperfect_target: int = 100_000
    perfect_chunk: int = 5_000
    imperfect_chunk: int = 5_000
    selfplay_episodes: int = 256
    selfplay_simulations: int = 128
    selfplay_epochs: int = 2
    batch_size: int = 4096
    autotune_batch: bool = True
    learning_rate: float = 5e-4
    weight_decay: float = 1e-4
    device: str = ""
    quick_gate_games: int = 50
    quick_gate_min_win_rate: float = 0.52
    teacher_gate_games: int = 200
    teacher_gate_min_win_rate: float = 0.90
    teacher_gate_required_streak: int = 1
    quick_gate_interval_updates: int = 3
    teacher_gate_interval_updates: int = 5
    sync_interval_updates: int = 10
    max_rounds_per_game: int = 200
    perfect_attempt_multiplier: int = 4
    imperfect_attempt_multiplier: int = 8
    seed_stride: int = 1_000_000
    policy_repo_id: str = ""


class LongRunCollectionState(FrozenModel):
    game: str
    generator_source: str
    output_path: str
    target_count: int
    current_count: int = 0
    chunk_size: int = 0
    chunks_completed: int = 0
    seed_cursor: int = 100000
    status: str = "pending"
    last_error: str = ""
    updated_at: str = ""


class LongRunTrainingState(FrozenModel):
    game: str
    output_dir: str
    rounds_completed: int = 0
    status: str = "pending"
    last_quick_win_rate: float = 0.0
    last_teacher_win_rate: float = 0.0
    teacher_pass_streak: int = 0
    latest_checkpoint: str = ""
    best_checkpoint: str = ""
    persisted_repo: str = ""
    autotuned_batch_size: int = 0
    last_error: str = ""
    updated_at: str = ""


class GameLongRunState(FrozenModel):
    job_name: str
    root_dir: str
    status: str = "pending"
    phase: str = "init"
    started_at: str = ""
    updated_at: str = ""
    perfect_training: dict[str, LongRunTrainingState] = Field(default_factory=dict)
    perfect_collection: dict[str, LongRunCollectionState] = Field(default_factory=dict)
    imperfect_training: dict[str, LongRunTrainingState] = Field(default_factory=dict)
    imperfect_collection: dict[str, LongRunCollectionState] = Field(default_factory=dict)
    model_sync: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
