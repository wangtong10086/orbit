from __future__ import annotations

from projects.openspiel_muzero_pt.games.affine_registry import DEFAULT_REGISTRY
from projects.openspiel_muzero_pt.pipelines.evaluate_vs_affine_mcts import _resolve_eval_mode_settings


def test_quick_mode_prefers_quick_budget_over_official():
    spec = DEFAULT_REGISTRY.get_spec(400_000_000)
    config = {
        "search": {"train_num_simulations": 8, "eval_num_simulations": 128},
        "eval": {
            "quick_games": 16,
            "quick_num_workers": 4,
            "quick_agent_simulations": 8,
            "quick_baseline_simulations": 16,
            "quick_baseline_rollouts": 2,
            "official_games": 1000,
            "official_num_workers": 8,
            "official_agent_simulations": 128,
            "official_baseline_simulations": 1000,
            "official_baseline_rollouts": 20,
            "quick_threshold_for_official": 0.90,
        },
    }
    settings = _resolve_eval_mode_settings(config, spec=spec, mode="quick")
    assert settings.mode == "quick"
    assert settings.games == 16
    assert settings.num_workers == 4
    assert settings.agent_simulations == 8
    assert settings.baseline_simulations == 16
    assert settings.baseline_rollouts == 2


def test_official_mode_keeps_affine_baseline_budget():
    spec = DEFAULT_REGISTRY.get_spec(400_000_000)
    config = {"search": {"eval_num_simulations": 128}, "eval": {"official_games": 1000}}
    settings = _resolve_eval_mode_settings(config, spec=spec, mode="official")
    assert settings.mode == "official"
    assert settings.games == 1000
    assert settings.agent_simulations == 128
    assert settings.baseline_simulations == spec.baseline_max_simulations
    assert settings.baseline_rollouts == spec.baseline_n_rollouts


def test_zero_eval_workers_expands_to_all_available_cores():
    spec = DEFAULT_REGISTRY.get_spec(400_000_000)
    config = {
        "search": {"eval_num_simulations": 32},
        "eval": {
            "quick_games": 16,
            "quick_num_workers": 0,
        },
    }
    settings = _resolve_eval_mode_settings(config, spec=spec, mode="quick")
    assert settings.num_workers >= 1


def test_zero_eval_worker_override_still_expands_when_games_override_is_present():
    spec = DEFAULT_REGISTRY.get_spec(400_000_000)
    config = {
        "search": {"eval_num_simulations": 32},
        "eval": {
            "quick_games": 16,
            "quick_num_workers": 4,
        },
    }
    settings = _resolve_eval_mode_settings(
        config,
        spec=spec,
        mode="quick",
        games_override=8,
        num_workers_override=0,
    )
    assert settings.games == 8
    assert settings.num_workers >= 1
