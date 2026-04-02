from __future__ import annotations

import numpy as np
import pytest
import torch

pyspiel = pytest.importorskip("pyspiel")

from projects.openspiel_muzero_pt.games.adapters import AffineOpenSpielAdapter
from projects.openspiel_muzero_pt.games.affine_registry import DEFAULT_REGISTRY
from projects.openspiel_muzero_pt.model.board_muzero import BoardMuZeroConfig, BoardMuZeroNet
from projects.openspiel_muzero_pt.runtime.inference import LocalModelInferenceClient, InferenceBatch, RecurrentInferenceBatch
from projects.openspiel_muzero_pt.search.batched_search import SearchConfig, SearchEngine


class CountingInferenceClient:
    def __init__(self, inner):
        self.inner = inner
        self.initial_calls = 0
        self.recurrent_calls = 0

    def initial(self, obs_batch: np.ndarray) -> InferenceBatch:
        self.initial_calls += 1
        return self.inner.initial(obs_batch)

    def recurrent(self, latent_batch: np.ndarray, action_planes_batch: np.ndarray) -> RecurrentInferenceBatch:
        self.recurrent_calls += 1
        return self.inner.recurrent(latent_batch, action_planes_batch)


def _build_search_engine(task_id: int):
    spec = DEFAULT_REGISTRY.get_spec(task_id)
    adapter = AffineOpenSpielAdapter(spec)
    model = BoardMuZeroNet(
        BoardMuZeroConfig(
            input_channels=spec.input_channels,
            board_height=spec.pad_h,
            board_width=spec.pad_w,
            action_dim=spec.action_dim,
            channels=32,
            repr_blocks=1,
            dyn_blocks=1,
            head_hidden=64,
        )
    )
    engine = SearchEngine(
        inference_client=LocalModelInferenceClient(model=model, device="cpu"),
        adapter=adapter,
        config=SearchConfig(train_num_simulations=8, eval_num_simulations=8, reanalyse_num_simulations=8, seed=0),
    )
    return spec, adapter, engine


@pytest.mark.parametrize("task_id", [400_000_000, 600_000_000, 700_000_000])
def test_search_returns_legal_policy_only(task_id: int):
    _, adapter, engine = _build_search_engine(task_id)
    state = adapter.new_initial_state()
    encoded = adapter.encode_state(state)
    result = engine.run(
        torch.from_numpy(encoded.obs).unsqueeze(0),
        torch.from_numpy(encoded.legal_mask).unsqueeze(0),
        [state],
        mode="eval",
    )
    chosen = int(result.chosen_action[0])
    legal = set(adapter.legal_actions_dense(state))
    assert chosen in legal
    illegal_mass = float(result.root_policy[0][encoded.legal_mask <= 0].sum())
    assert np.isclose(illegal_mass, 0.0)


@pytest.mark.parametrize("task_id", [400_000_000, 600_000_000, 700_000_000])
def test_search_handles_terminal_state(task_id: int):
    _, adapter, engine = _build_search_engine(task_id)
    state = adapter.new_initial_state()
    rng = np.random.default_rng(0)
    while not state.is_terminal():
        legal = adapter.legal_actions_dense(state)
        assert legal
        adapter.apply_dense_action(state, int(rng.choice(legal)))
    encoded = adapter.encode_state(state)
    result = engine.run(
        torch.from_numpy(encoded.obs).unsqueeze(0),
        torch.from_numpy(encoded.legal_mask).unsqueeze(0),
        [state],
        mode="eval",
    )
    assert result.root_policy.shape == (1, adapter.spec.action_dim)
    assert result.root_value.shape == (1,)


def test_search_can_reuse_promoted_child_root_without_new_initial_inference():
    spec = DEFAULT_REGISTRY.get_spec(400_000_000)
    adapter = AffineOpenSpielAdapter(spec)
    model = BoardMuZeroNet(
        BoardMuZeroConfig(
            input_channels=spec.input_channels,
            board_height=spec.pad_h,
            board_width=spec.pad_w,
            action_dim=spec.action_dim,
            channels=32,
            repr_blocks=1,
            dyn_blocks=1,
            head_hidden=64,
        )
    )
    counting_client = CountingInferenceClient(LocalModelInferenceClient(model=model, device="cpu"))
    engine = SearchEngine(
        inference_client=counting_client,
        adapter=adapter,
        config=SearchConfig(train_num_simulations=8, eval_num_simulations=8, reanalyse_num_simulations=8, seed=0),
    )

    state = adapter.new_initial_state()
    encoded = adapter.encode_state(state)
    first = engine.run(
        torch.from_numpy(encoded.obs).unsqueeze(0),
        torch.from_numpy(encoded.legal_mask).unsqueeze(0),
        [state],
        mode="eval",
    )
    assert counting_client.initial_calls == 1

    action = int(first.chosen_action[0])
    next_state = state.clone()
    adapter.apply_dense_action(next_state, action)
    next_encoded = adapter.encode_state(next_state)
    reused_root = engine.promote_child_root(root=first.root_nodes[0], action=action, next_state=next_state)

    second = engine.run(
        torch.from_numpy(next_encoded.obs).unsqueeze(0),
        torch.from_numpy(next_encoded.legal_mask).unsqueeze(0),
        [next_state],
        mode="eval",
        encoded_state_batch=[next_encoded],
        root_nodes=[reused_root],
    )
    assert counting_client.initial_calls == 1
    assert second.root_policy.shape == (1, spec.action_dim)
