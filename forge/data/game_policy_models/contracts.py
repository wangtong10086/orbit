"""Contracts shared across GAME self-play components."""

from __future__ import annotations

from pydantic import Field

from forge.foundation.schema import FrozenModel


class ReplayBufferReport(FrozenModel):
    game: str
    output: str
    episodes: int = 0
    rows: int = 0
    input_dim: int = 0
    action_dim: int = 0
    simulations: int = 0
    generator_family: str = ""
    unique_state_keys: int = 0
    unique_action_support: int = 0
    duplicate_ratio: float = 0.0
    mean_policy_entropy: float = 0.0
    step_depth_histogram: dict[str, int] = Field(default_factory=dict)


class ArenaEvalReport(FrozenModel):
    game: str
    opponent: str
    output: str = ""
    games: int = 0
    wins: int = 0
    losses: int = 0
    draws: int = 0
    win_rate: float = 0.0
    passed: bool = False
    checkpoint_path: str = ""
    opponent_checkpoint: str = ""


class SelfPlayTrainReport(FrozenModel):
    game: str
    output_dir: str
    latest_checkpoint: str = ""
    best_checkpoint: str = ""
    replay_path: str = ""
    replay_rows: int = 0
    selfplay_episodes: int = 0
    train_epochs: int = 0
    batch_size: int = 0
    device: str = ""
    quick_eval: ArenaEvalReport | None = None
    teacher_eval: ArenaEvalReport | None = None
    promoted: bool = False
    teacher_pass_streak: int = 0
    persisted_repo: str = ""
    training_route: str = "selfplay"


class SelfPlayLongRunReport(FrozenModel):
    game: str
    output_dir: str
    completed: bool = False
    rounds_completed: int = 0
    max_rounds: int = 0
    latest_checkpoint: str = ""
    best_checkpoint: str = ""
    last_quick_win_rate: float = 0.0
    last_teacher_win_rate: float = 0.0
    teacher_pass_streak: int = 0
    persisted_repo: str = ""
    final_report: SelfPlayTrainReport | None = None
    stop_reason: str = ""


class SelfPlayStatusEntry(FrozenModel):
    game: str
    output_dir: str
    exists: bool = False
    latest_exists: bool = False
    best_exists: bool = False
    status: dict[str, object] = Field(default_factory=dict)
    latest_metadata: dict[str, object] = Field(default_factory=dict)
    best_metadata: dict[str, object] = Field(default_factory=dict)
    persisted_repo: str = ""


class SelfPlayStatusState(FrozenModel):
    game: str
    output_dir: str
    training_route: str = "selfplay"
    latest_checkpoint: str = ""
    best_checkpoint: str = ""
    replay_path: str = ""
    replay_rows: int = 0
    selfplay_episodes: int = 0
    train_epochs: int = 0
    quick_gate_games: int = 50
    teacher_gate_games: int = 200
    last_quick_win_rate: float = 0.0
    last_teacher_win_rate: float = 0.0
    teacher_pass_streak: int = 0
    best_history: list[str] = Field(default_factory=list)
    replay_window_rounds: int = 20
    replay_window_rows: int = 50000
    recent_fraction: float = 0.7
    coverage: dict[str, object] = Field(default_factory=dict)
    persisted_repo: str = ""
    learner_updates: int = 0
    last_policy_loss: float = 0.0
    last_value_loss: float = 0.0
    last_entropy: float = 0.0
    last_checkpoint_at: str = ""
    last_replay_flush_at: str = ""
    autotuned_batch_size: int = 0
    updated_at: str = ""


class SelfPlayHeartbeat(FrozenModel):
    game: str
    output_dir: str
    status: str = "running"
    learner_updates: int = 0
    rows_generated_total: int = 0
    rows_generated_last_10m: int = 0
    rows_consumed_total: int = 0
    last_policy_loss: float = 0.0
    last_value_loss: float = 0.0
    last_entropy: float = 0.0
    last_quick_win_rate: float = 0.0
    last_teacher_win_rate: float = 0.0
    gpu_util_avg_5m: float = 0.0
    gpu_mem_avg_5m: float = 0.0
    cpu_util_avg_5m: float = 0.0
    actors_alive: int = 0
    last_checkpoint_at: str = ""
    last_replay_flush_at: str = ""
    autotuned_batch_size: int = 0
    updated_at: str = ""
