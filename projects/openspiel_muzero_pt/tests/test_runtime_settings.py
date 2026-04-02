from __future__ import annotations

from projects.openspiel_muzero_pt.runtime.settings import (
    parse_actor_runtime_settings,
    parse_gpu_coordinator_runtime_settings,
)


def test_actor_runtime_settings_prefer_explicit_actor_section():
    config = {
        "train": {
            "actor_workers": 4,
            "parallel_games_per_actor": 8,
            "actor_games_per_chunk": 8,
            "actor_queue_size": 16,
        },
        "actors": {
            "workers": 12,
            "parallel_games_per_actor": 24,
            "games_per_chunk": 6,
            "result_queue_size": 64,
        },
    }
    settings = parse_actor_runtime_settings(config)
    assert settings.workers == 12
    assert settings.parallel_games_per_actor == 24
    assert settings.games_per_chunk == 6
    assert settings.result_queue_size == 64


def test_gpu_coordinator_settings_support_new_runtime_section():
    config = {
        "train": {"snapshot_sync_interval": 2000},
        "runtime": {
            "gpu_coordinator": {
                "snapshot_sync_interval": 500,
                "initial_max_batch_items": 128,
                "recurrent_max_batch_items": 256,
            }
        },
    }
    settings = parse_gpu_coordinator_runtime_settings(config)
    assert settings.snapshot_sync_interval == 500
    assert settings.initial_max_batch_items == 128
    assert settings.recurrent_max_batch_items == 256
