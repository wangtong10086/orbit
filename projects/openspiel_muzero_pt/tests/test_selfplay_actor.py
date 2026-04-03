from __future__ import annotations

import numpy as np
import pytest
import torch

pyspiel = pytest.importorskip("pyspiel")

from projects.openspiel_muzero_pt.games.adapters import AffineOpenSpielAdapter
from projects.openspiel_muzero_pt.games.affine_registry import DEFAULT_REGISTRY
from projects.openspiel_muzero_pt.model.board_muzero import BoardMuZeroConfig, BoardMuZeroNet
from projects.openspiel_muzero_pt.pipelines.selfplay_actor import (
    _advance_selfplay_slots_streaming,
    _build_actor_heartbeat_payload,
    _spawn_slot,
    generate_selfplay_games,
    pack_selfplay_games,
    should_flush_selfplay_chunk,
)
from projects.openspiel_muzero_pt.runtime.inference import LocalModelInferenceClient
from projects.openspiel_muzero_pt.search.batched_search import SearchConfig, SearchEngine


def test_generate_selfplay_games_returns_requested_game_count():
    spec = DEFAULT_REGISTRY.get_spec(400_000_000)
    adapter = AffineOpenSpielAdapter(spec)
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
    search = SearchEngine(
        inference_client=LocalModelInferenceClient(model=model, device="cpu"),
        adapter=adapter,
        config=SearchConfig(train_num_simulations=4, eval_num_simulations=4, reanalyse_num_simulations=4, seed=0),
    )
    games = generate_selfplay_games(
        adapter=adapter,
        search_engine=search,
        num_games=3,
        seed=0,
        num_parallel_games=2,
    )
    assert len(games) == 3
    assert all(game.samples for game in games)
    assert all(game.mean_search_ms >= 0.0 for game in games)
    for game in games:
        for sample in game.samples:
            assert sample.next_obs.shape == sample.obs.shape
            assert sample.next_legal_mask.shape == sample.legal_mask.shape
            assert sample.next_policy_target.shape == sample.policy_target.shape
            assert sample.recurrent_mask in {0.0, 1.0}
            if sample.recurrent_mask == 0.0:
                assert float(sample.next_policy_target.sum()) == pytest.approx(0.0)
                assert sample.next_value_target == pytest.approx(0.0)


def test_selfplay_samples_match_replayed_state_targets():
    spec = DEFAULT_REGISTRY.get_spec(400_000_000)
    adapter = AffineOpenSpielAdapter(spec)
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
    search = SearchEngine(
        inference_client=LocalModelInferenceClient(model=model, device="cpu"),
        adapter=adapter,
        config=SearchConfig(train_num_simulations=4, eval_num_simulations=4, reanalyse_num_simulations=4, seed=0),
    )
    game = generate_selfplay_games(
        adapter=adapter,
        search_engine=search,
        num_games=1,
        seed=1,
        num_parallel_games=1,
    )[0]

    state = adapter.new_initial_state()
    for sample in game.samples:
        encoded = adapter.encode_state(state)
        assert np.allclose(sample.obs, encoded.obs)
        assert np.allclose(sample.legal_mask, encoded.legal_mask)
        current_player = int(state.current_player())
        next_state = state.clone()
        adapter.apply_dense_action(next_state, int(sample.action))
        next_encoded = adapter.encode_state(next_state)
        assert np.allclose(sample.next_obs, next_encoded.obs)
        assert np.allclose(sample.next_legal_mask, next_encoded.legal_mask)
        final_returns = game.outcome, -game.outcome
        assert sample.value_target == pytest.approx(float(final_returns[current_player]))
        if sample.recurrent_mask > 0.0:
            assert sample.next_value_target == pytest.approx(float(final_returns[int(next_state.current_player())]))
            assert float(sample.next_policy_target.sum()) > 0.0
        else:
            assert next_state.is_terminal()
            assert sample.next_value_target == pytest.approx(0.0)
        state = next_state


def test_pack_selfplay_games_reports_chunk_metadata():
    spec = DEFAULT_REGISTRY.get_spec(400_000_000)
    adapter = AffineOpenSpielAdapter(spec)
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
    search = SearchEngine(
        inference_client=LocalModelInferenceClient(model=model, device="cpu"),
        adapter=adapter,
        config=SearchConfig(train_num_simulations=4, eval_num_simulations=4, reanalyse_num_simulations=4, seed=0),
    )
    games = generate_selfplay_games(
        adapter=adapter,
        search_engine=search,
        num_games=2,
        seed=2,
        num_parallel_games=2,
    )
    chunk = pack_selfplay_games(games)
    assert chunk["games_generated"] == 2
    assert int(chunk["positions_generated"]) == sum(len(game.samples) for game in games)
    assert float(chunk["mean_search_ms"]) >= 0.0
    payload = chunk["payload"]
    assert int(payload["action"].shape[0]) == int(chunk["positions_generated"])


def test_should_flush_selfplay_chunk_prefers_positions_then_games_then_time():
    assert (
        should_flush_selfplay_chunk(
            staged_positions=128,
            staged_games=1,
            last_flush_at=10.0,
            now=10.2,
            flush_positions=64,
            flush_games=4,
            flush_seconds=10.0,
        )
        == "positions"
    )
    assert (
        should_flush_selfplay_chunk(
            staged_positions=32,
            staged_games=4,
            last_flush_at=10.0,
            now=10.2,
            flush_positions=64,
            flush_games=4,
            flush_seconds=10.0,
        )
        == "games"
    )
    assert (
        should_flush_selfplay_chunk(
            staged_positions=32,
            staged_games=1,
            last_flush_at=10.0,
            now=12.5,
            flush_positions=64,
            flush_games=4,
            flush_seconds=2.0,
        )
        == "time"
    )
    assert (
        should_flush_selfplay_chunk(
            staged_positions=0,
            staged_games=0,
            last_flush_at=10.0,
            now=20.0,
            flush_positions=64,
            flush_games=4,
            flush_seconds=2.0,
        )
        is None
    )


def test_actor_heartbeat_payload_summarizes_active_slots():
    now = 100.0
    active = [
        {"rows": [1, 2], "pending_row": object(), "started_at": 90.0},
        {"rows": [1], "pending_row": None, "started_at": 80.0},
    ]
    payload = _build_actor_heartbeat_payload(
        worker_id=3,
        active=active,
        completed_games_since_last_flush=5,
        staged_ready_rows=11,
        staged_terminal_rows=17,
        now=now,
    )
    assert payload["type"] == "actor_heartbeat"
    assert payload["worker_id"] == 3
    assert payload["active_slots"] == 2
    assert payload["completed_games_since_last_flush"] == 5
    assert payload["staged_ready_rows"] == 11
    assert payload["pending_rows_in_active_slots"] == 4
    assert payload["staged_terminal_rows"] == 17
    assert payload["oldest_active_game_age_sec"] == pytest.approx(20.0)
    assert payload["mean_active_game_length_so_far"] == pytest.approx(2.0)


def test_streaming_selfplay_defers_samples_until_game_completion():
    spec = DEFAULT_REGISTRY.get_spec(600_000_000)
    adapter = AffineOpenSpielAdapter(spec)
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
    search = SearchEngine(
        inference_client=LocalModelInferenceClient(model=model, device="cpu"),
        adapter=adapter,
        config=SearchConfig(train_num_simulations=4, eval_num_simulations=4, reanalyse_num_simulations=4, seed=0),
    )
    active = [_spawn_slot(adapter, 0)]

    first = _advance_selfplay_slots_streaming(adapter=adapter, search_engine=search, active=active)
    assert first["games_generated"] == 0
    assert first["ready_samples"] == []
    assert active
    assert active[0]["pending_row"] is not None

    # Samples are deferred until game completion (value_target uses true outcome)
    second = _advance_selfplay_slots_streaming(adapter=adapter, search_engine=search, active=active)
    assert second["games_generated"] == 0
    assert second["terminal_rows_emitted"] == 0
    # No samples emitted yet — accumulated in slot until game finishes
    assert len(second["ready_samples"]) == 0

    # Run until game completes
    all_samples = []
    while active:
        step = _advance_selfplay_slots_streaming(adapter=adapter, search_engine=search, active=active)
        all_samples.extend(step["ready_samples"])
        if step["games_generated"] > 0:
            break

    assert len(all_samples) > 0
    # Verify value_targets use the true game outcome, not search estimates
    game_state = adapter.new_initial_state()
    for sample in all_samples:
        adapter.apply_dense_action(game_state, int(sample.action))
    assert game_state.is_terminal()
    final_returns = game_state.returns()
    for sample in all_samples:
        # All samples from the same game should have value_target matching final outcome
        assert sample.value_target == pytest.approx(final_returns[0]) or sample.value_target == pytest.approx(final_returns[1])
