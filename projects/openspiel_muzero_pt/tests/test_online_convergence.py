from __future__ import annotations

from projects.openspiel_muzero_pt.pipelines.train_online import _resolve_replay_batch_sizes, _update_convergence_state


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


def test_replay_batch_sizes_follow_configured_ratio() -> None:
    live, expert = _resolve_replay_batch_sizes(
        batch_size=10,
        replay_ratio={"live": 0.6, "expert": 0.4},
        expert_available=True,
    )
    assert live == 6
    assert expert == 4


def test_replay_batch_sizes_force_all_live_when_expert_missing() -> None:
    live, expert = _resolve_replay_batch_sizes(
        batch_size=10,
        replay_ratio={"live": 0.2, "expert": 0.8},
        expert_available=False,
    )
    assert live == 10
    assert expert == 0


def test_replay_batch_sizes_allow_single_sided_ratios() -> None:
    assert _resolve_replay_batch_sizes(batch_size=10, replay_ratio={"live": 1.0, "expert": 0.0}, expert_available=True) == (10, 0)
    assert _resolve_replay_batch_sizes(batch_size=10, replay_ratio={"live": 0.0, "expert": 1.0}, expert_available=True) == (0, 10)


def test_replay_batch_sizes_keep_both_sides_present_for_small_batches() -> None:
    live, expert = _resolve_replay_batch_sizes(
        batch_size=2,
        replay_ratio={"live": 0.9, "expert": 0.1},
        expert_available=True,
    )
    assert live == 1
    assert expert == 1
