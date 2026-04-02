from __future__ import annotations

import numpy as np
import pytest
import torch

pyspiel = pytest.importorskip("pyspiel")

from projects.openspiel_muzero_pt.games.adapters import AffineOpenSpielAdapter
from projects.openspiel_muzero_pt.games.affine_registry import DEFAULT_REGISTRY
from projects.openspiel_muzero_pt.model.board_muzero import BoardMuZeroConfig, BoardMuZeroNet
from projects.openspiel_muzero_pt.runtime.inference import LocalModelInferenceClient
from projects.openspiel_muzero_pt.search.batched_search import SearchConfig, SearchEngine


def _build_search_engine():
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
    engine = SearchEngine(
        inference_client=LocalModelInferenceClient(model=model, device="cpu"),
        adapter=adapter,
        config=SearchConfig(train_num_simulations=8, eval_num_simulations=8, reanalyse_num_simulations=8, seed=0),
    )
    return spec, adapter, engine


def test_othello_search_returns_legal_policy_only():
    _, adapter, engine = _build_search_engine()
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


def test_othello_search_handles_terminal_state():
    _, adapter, engine = _build_search_engine()
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
