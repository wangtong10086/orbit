from __future__ import annotations

import numpy as np

from projects.openspiel_muzero_pt.replay.ring_buffer import ArrayRingBuffer


def _payload(rows: int) -> dict[str, np.ndarray]:
    return {
        "obs": np.arange(rows * 2, dtype=np.float32).reshape(rows, 2),
        "action": np.arange(rows, dtype=np.int64),
    }


def test_ring_buffer_truncates_to_capacity():
    buffer = ArrayRingBuffer(capacity=5)
    buffer.append_chunk(_payload(3))
    buffer.append_chunk(_payload(4))
    assert len(buffer) == 5
    materialized = buffer.materialize()
    assert materialized["action"].tolist() == [2, 0, 1, 2, 3]
    batch = buffer.sample_batch(5, rng=np.random.default_rng(0))
    assert batch["obs"].shape == (5, 2)


def test_ring_buffer_returns_requested_batch_size():
    buffer = ArrayRingBuffer(capacity=8)
    buffer.append_chunk(_payload(8))
    rng = np.random.default_rng(0)
    batch = buffer.sample_batch(3, rng=rng)
    assert batch["obs"].shape == (3, 2)
    assert batch["action"].shape == (3,)


def test_ring_buffer_overwrites_oldest_rows_in_order():
    buffer = ArrayRingBuffer(capacity=5)
    buffer.append_chunk(_payload(4))
    buffer.append_chunk(_payload(2))
    materialized = buffer.materialize()
    assert materialized["action"].tolist() == [1, 2, 3, 0, 1]
