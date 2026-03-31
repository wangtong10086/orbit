"""Control-plane helpers for GAME self-play evaluation and gating."""

from __future__ import annotations

import numpy as np

from forge.data.game_policy_models.artifacts import _arena_path
from forge.data.game_policy_models.contracts import ArenaEvalReport, SelfPlayStatusState


def _make_arena_report(
    *,
    game_name: str,
    opponent: str,
    output_dir: str,
    checkpoint_path: str,
    opponent_checkpoint: str,
    games: int = 0,
    wins: int = 0,
    losses: int = 0,
    draws: int = 0,
    win_rate: float = 0.0,
    passed: bool = False,
) -> ArenaEvalReport:
    return ArenaEvalReport(
        game=game_name,
        opponent=opponent,
        output=str(_arena_path(output_dir, f"{opponent}_eval")),
        games=games,
        wins=wins,
        losses=losses,
        draws=draws,
        win_rate=win_rate,
        passed=passed,
        checkpoint_path=checkpoint_path,
        opponent_checkpoint=opponent_checkpoint,
    )


def _required_wins_for_threshold(games: int, min_win_rate: float) -> int:
    return int(np.ceil(float(min_win_rate) * max(int(games), 1)))


def _phase_name(*, status: SelfPlayStatusState, teacher_gate_min_win_rate: float) -> str:
    if status.teacher_pass_streak > 0 or status.last_teacher_win_rate >= teacher_gate_min_win_rate * 0.8:
        return "gate_push"
    if status.learner_updates < 3:
        return "ramp"
    return "stabilize"


def _phase_simulations(
    *,
    base_simulations: int,
    profile: dict[str, object],
    phase: str,
) -> int:
    if phase == "ramp":
        return max(2, int(np.ceil(base_simulations * float(profile.get("simulation_scale_ramp", 0.5)))))
    if phase == "gate_push":
        return max(base_simulations, int(np.ceil(base_simulations * float(profile.get("simulation_scale_gate_push", 1.5)))))
    return int(base_simulations)


def _cheap_teacher_threshold(*, teacher_gate_min_win_rate: float, profile: dict[str, object]) -> float:
    return float(profile.get("cheap_teacher_gate_min_win_rate", max(0.5, teacher_gate_min_win_rate * 0.8)))


__all__ = [
    "_cheap_teacher_threshold",
    "_make_arena_report",
    "_phase_name",
    "_phase_simulations",
    "_required_wins_for_threshold",
]
