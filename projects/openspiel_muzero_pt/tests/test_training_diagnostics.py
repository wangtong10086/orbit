from __future__ import annotations

import numpy as np
import pytest
import torch

pyspiel = pytest.importorskip("pyspiel")

from projects.openspiel_muzero_pt.games.action_codecs import get_action_codec
from projects.openspiel_muzero_pt.games.adapters import AffineOpenSpielAdapter
from projects.openspiel_muzero_pt.games.affine_registry import DEFAULT_REGISTRY
from projects.openspiel_muzero_pt.model.board_muzero import BoardMuZeroConfig, BoardMuZeroNet
from projects.openspiel_muzero_pt.pipelines.learner import OnlineLearner


def _build_model_and_adapter():
    spec = DEFAULT_REGISTRY.get_spec(400_000_000)
    adapter = AffineOpenSpielAdapter(spec)
    torch.manual_seed(0)
    model = BoardMuZeroNet(
        BoardMuZeroConfig(
            input_channels=spec.input_channels,
            board_height=spec.pad_h,
            board_width=spec.pad_w,
            action_dim=spec.action_dim,
            channels=16,
            repr_blocks=1,
            dyn_blocks=1,
            head_hidden=32,
        )
    )
    return spec, adapter, model


def _build_consistency_batch(model: BoardMuZeroNet, adapter: AffineOpenSpielAdapter) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    spec = adapter.spec
    codec = get_action_codec(spec)
    state = adapter.new_initial_state()
    encoded = adapter.encode_state(state)
    action = adapter.legal_actions_dense(state)[0]
    next_state = state.clone()
    adapter.apply_dense_action(next_state, action)
    next_encoded = adapter.encode_state(next_state)

    obs = torch.from_numpy(encoded.obs).unsqueeze(0)
    legal_mask = torch.from_numpy(encoded.legal_mask).unsqueeze(0)
    with torch.no_grad():
        initial = model.initial_inference(obs)
        masked_logits = initial.policy_logits.masked_fill(legal_mask <= 0, -1e9)
        action_planes = codec.to_action_planes(action, spec).unsqueeze(0)
        recurrent = model.recurrent_inference(initial.latent, action_planes)
        next_initial = model.initial_inference(torch.from_numpy(next_encoded.obs).unsqueeze(0))
        next_mask = torch.from_numpy(next_encoded.legal_mask).unsqueeze(0)
        next_masked_logits = next_initial.policy_logits.masked_fill(next_mask <= 0, -1e9)
        policy_target = torch.softmax(masked_logits, dim=-1).cpu().numpy().astype(np.float32)
        value_target = initial.value.cpu().numpy().astype(np.float32)
        reward_target = recurrent.reward.cpu().numpy().astype(np.float32)
        next_policy_target = torch.softmax(next_masked_logits, dim=-1).cpu().numpy().astype(np.float32)
        next_value_target = next_initial.value.cpu().numpy().astype(np.float32)

    batch = {
        "obs": np.expand_dims(encoded.obs, axis=0).astype(np.float32),
        "legal_mask": np.expand_dims(encoded.legal_mask, axis=0).astype(np.float32),
        "action": np.asarray([action], dtype=np.int64),
        "next_obs": np.expand_dims(next_encoded.obs, axis=0).astype(np.float32),
        "next_legal_mask": np.expand_dims(next_encoded.legal_mask, axis=0).astype(np.float32),
        "next_policy_target": next_policy_target,
        "next_value_target": next_value_target,
        "policy_target": policy_target,
        "value_target": value_target,
        "reward_target": reward_target,
        "phase": np.asarray([encoded.phase], dtype=np.float32),
        "move_index": np.asarray([encoded.move_index], dtype=np.int64),
        "variant_id": np.asarray([spec.variant_index], dtype=np.int64),
        "weight_version": np.asarray([0], dtype=np.int64),
    }
    without_recurrent = dict(batch)
    without_recurrent["recurrent_mask"] = np.asarray([0.0], dtype=np.float32)
    with_recurrent = dict(batch)
    with_recurrent["recurrent_mask"] = np.asarray([1.0], dtype=np.float32)
    return without_recurrent, with_recurrent


def test_online_learner_uses_recurrent_consistency_targets():
    spec, adapter, base_model = _build_model_and_adapter()
    without_recurrent, with_recurrent = _build_consistency_batch(base_model, adapter)

    model_without = BoardMuZeroNet(
        BoardMuZeroConfig(
            input_channels=spec.input_channels,
            board_height=spec.pad_h,
            board_width=spec.pad_w,
            action_dim=spec.action_dim,
            channels=16,
            repr_blocks=1,
            dyn_blocks=1,
            head_hidden=32,
        )
    )
    model_with = BoardMuZeroNet(
        BoardMuZeroConfig(
            input_channels=spec.input_channels,
            board_height=spec.pad_h,
            board_width=spec.pad_w,
            action_dim=spec.action_dim,
            channels=16,
            repr_blocks=1,
            dyn_blocks=1,
            head_hidden=32,
        )
    )
    model_without.load_state_dict(base_model.state_dict())
    model_with.load_state_dict(base_model.state_dict())
    learner_without = OnlineLearner(
        model=model_without,
        adapter=adapter,
        optimizer=torch.optim.AdamW(model_without.parameters(), lr=0.0),
        device="cpu",
    )
    learner_with = OnlineLearner(
        model=model_with,
        adapter=adapter,
        optimizer=torch.optim.AdamW(model_with.parameters(), lr=0.0),
        device="cpu",
    )

    metrics_without = learner_without.train_batch(without_recurrent)
    metrics_with = learner_with.train_batch(with_recurrent)

    assert metrics_without.recurrent_policy_loss == pytest.approx(0.0, abs=1e-8)
    assert metrics_without.recurrent_value_loss == pytest.approx(0.0, abs=1e-8)
    assert metrics_without.latent_loss == pytest.approx(0.0, abs=1e-8)
    assert metrics_with.recurrent_policy_loss > 0.0
    assert metrics_with.recurrent_value_loss >= 0.0
    assert metrics_with.latent_loss > 0.0
    assert metrics_with.loss > metrics_without.loss
