from __future__ import annotations

from projects.openspiel_muzero_pt.pipelines.train_online import _update_convergence_state


def test_convergence_streak_increments_only_when_gate_passes() -> None:
    report = {"games_completed": 200, "win_rate": 0.91}
    passed, streak, converged = _update_convergence_state(
        report=report,
        quick_threshold=0.90,
        required_games=200,
        required_passes=2,
        current_streak=0,
    )
    assert passed is True
    assert streak == 1
    assert converged is False


def test_convergence_requires_strictly_more_than_threshold() -> None:
    report = {"games_completed": 200, "win_rate": 0.90}
    passed, streak, converged = _update_convergence_state(
        report=report,
        quick_threshold=0.90,
        required_games=200,
        required_passes=2,
        current_streak=1,
    )
    assert passed is False
    assert streak == 0
    assert converged is False


def test_convergence_triggers_after_two_passes() -> None:
    report = {"games_completed": 200, "win_rate": 0.95}
    passed, streak, converged = _update_convergence_state(
        report=report,
        quick_threshold=0.90,
        required_games=200,
        required_passes=2,
        current_streak=1,
    )
    assert passed is True
    assert streak == 2
    assert converged is True
