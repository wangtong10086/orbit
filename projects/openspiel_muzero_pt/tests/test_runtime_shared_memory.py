from __future__ import annotations

import numpy as np

from projects.openspiel_muzero_pt.runtime.shared_memory import InferenceWorkerSharedBuffers, ReplayChunkSharedBuffers


def test_shared_buffers_roundtrip_initial_and_recurrent():
    buffers = InferenceWorkerSharedBuffers.create(
        max_batch_size=4,
        obs_shape=(5, 3, 3),
        latent_shape=(7, 3, 3),
        action_planes_shape=(3, 3, 3),
        action_dim=11,
    )
    attached = InferenceWorkerSharedBuffers.attach(buffers.export())
    try:
        obs = np.arange(2 * 5 * 3 * 3, dtype=np.float32).reshape(2, 5, 3, 3)
        batch_size = attached.write_initial_request(obs)
        read_obs = buffers.read_initial_request(batch_size).copy()
        assert np.array_equal(read_obs, obs)

        latent = np.ones((2, 7, 3, 3), dtype=np.float32)
        policy = np.full((2, 11), 2.0, dtype=np.float32)
        value = np.asarray([0.25, -0.5], dtype=np.float32)
        buffers.write_initial_response(latent=latent, policy_logits=policy, value=value, batch_size=2)
        initial_response = attached.read_initial_response(2)
        assert np.array_equal(initial_response["latent"], latent)
        assert np.array_equal(initial_response["policy_logits"], policy)
        assert np.array_equal(initial_response["value"], value)

        req_latent = np.full((3, 7, 3, 3), 3.0, dtype=np.float32)
        req_actions = np.full((3, 3, 3, 3), 4.0, dtype=np.float32)
        batch_size = attached.write_recurrent_request(req_latent, req_actions)
        read_latent, read_actions = buffers.read_recurrent_request(batch_size)
        assert np.array_equal(read_latent.copy(), req_latent)
        assert np.array_equal(read_actions.copy(), req_actions)

        next_latent = np.full((3, 7, 3, 3), 5.0, dtype=np.float32)
        reward = np.asarray([0.1, 0.2, 0.3], dtype=np.float32)
        policy = np.full((3, 11), 6.0, dtype=np.float32)
        value = np.asarray([0.4, 0.5, 0.6], dtype=np.float32)
        buffers.write_recurrent_response(
            latent=next_latent,
            reward=reward,
            policy_logits=policy,
            value=value,
            batch_size=3,
        )
        recurrent_response = attached.read_recurrent_response(3)
        assert np.array_equal(recurrent_response["latent"], next_latent)
        assert np.array_equal(recurrent_response["reward"], reward)
        assert np.array_equal(recurrent_response["policy_logits"], policy)
        assert np.array_equal(recurrent_response["value"], value)
    finally:
        attached.close()
        buffers.close()
        buffers.unlink()


def test_replay_chunk_shared_buffers_roundtrip():
    buffers = ReplayChunkSharedBuffers.create(
        slot_count=2,
        max_rows_per_slot=5,
        obs_shape=(4, 3, 3),
        action_dim=11,
    )
    attached = ReplayChunkSharedBuffers.attach(buffers.export())
    try:
        payload = {
            "obs": np.arange(3 * 4 * 3 * 3, dtype=np.float32).reshape(3, 4, 3, 3),
            "legal_mask": np.full((3, 11), 1.0, dtype=np.float32),
            "action": np.asarray([1, 2, 3], dtype=np.int64),
            "next_obs": np.full((3, 4, 3, 3), 2.0, dtype=np.float32),
            "next_legal_mask": np.full((3, 11), 3.0, dtype=np.float32),
            "next_policy_target": np.full((3, 11), 4.0, dtype=np.float32),
            "next_value_target": np.asarray([0.1, 0.2, 0.3], dtype=np.float32),
            "recurrent_mask": np.asarray([1.0, 0.0, 1.0], dtype=np.float32),
            "policy_target": np.full((3, 11), 5.0, dtype=np.float32),
            "value_target": np.asarray([0.4, 0.5, 0.6], dtype=np.float32),
            "reward_target": np.asarray([0.7, 0.8, 0.9], dtype=np.float32),
            "phase": np.asarray([0.0, 0.5, 1.0], dtype=np.float32),
            "move_index": np.asarray([4, 5, 6], dtype=np.int64),
            "variant_id": np.asarray([7, 7, 7], dtype=np.int64),
            "weight_version": np.asarray([8, 8, 8], dtype=np.int64),
        }
        rows = attached.write_slot(1, payload)
        roundtrip = buffers.read_slot(1, rows)
        for key, value in payload.items():
            assert np.array_equal(roundtrip[key], value)
    finally:
        attached.close()
        buffers.close()
        buffers.unlink()
