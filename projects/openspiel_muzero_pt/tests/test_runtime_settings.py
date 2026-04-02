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
            "active_games_per_actor": 24,
            "chunk_flush_positions": 256,
            "chunk_flush_games": 6,
            "chunk_flush_seconds": 1.5,
            "result_queue_size": 64,
            "result_queue_slots": 3,
        },
    }
    settings = parse_actor_runtime_settings(config)
    assert settings.workers == 12
    assert settings.active_games_per_actor == 24
    assert settings.chunk_flush_positions == 256
    assert settings.chunk_flush_games == 6
    assert settings.chunk_flush_seconds == 1.5
    assert settings.result_queue_size == 64
    assert settings.result_queue_slots == 3


def test_actor_runtime_settings_support_legacy_fallbacks():
    config = {
        "train": {
            "actor_workers": 4,
            "parallel_games_per_actor": 8,
            "actor_games_per_chunk": 5,
            "actor_queue_size": 32,
        },
        "actors": {
            "parallel_games_per_actor": 16,
            "games_per_chunk": 7,
        },
    }
    settings = parse_actor_runtime_settings(config)
    assert settings.workers == 4
    assert settings.active_games_per_actor == 16
    assert settings.chunk_flush_positions == 0
    assert settings.chunk_flush_games == 7
    assert settings.result_queue_size == 32
    assert settings.result_queue_slots == 2


def test_gpu_coordinator_settings_support_new_runtime_section():
    config = {
        "train": {"snapshot_sync_interval": 2000},
        "runtime": {
            "gpu_coordinator": {
                "snapshot_sync_interval": 500,
                "initial_max_batch_items": 128,
                "recurrent_max_batch_items": 256,
                "train_microbatch_size": 64,
                "max_train_microbatches_per_turn": 3,
                "inference_low_watermark": 9,
            }
        },
    }
    settings = parse_gpu_coordinator_runtime_settings(config)
    assert settings.snapshot_sync_interval == 500
    assert settings.initial_max_batch_items == 128
    assert settings.recurrent_max_batch_items == 256
    assert settings.train_microbatch_size == 64
    assert settings.max_train_microbatches_per_turn == 3
    assert settings.inference_low_watermark == 9
