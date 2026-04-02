from __future__ import annotations

from dataclasses import dataclass
import queue
import random
import time
from typing import Any

import numpy as np

from projects.openspiel_muzero_pt.config_utils import build_search_engine, load_yaml_config, resolve_spec_from_config
from projects.openspiel_muzero_pt.games.adapters import AffineOpenSpielAdapter
from projects.openspiel_muzero_pt.replay.expert_buffer import ReplaySample, pack_samples
from projects.openspiel_muzero_pt.runtime.inference import BrokeredInferenceClient
from projects.openspiel_muzero_pt.search.batched_search import SearchEngine


@dataclass(slots=True)
class SelfPlayGame:
    episode_id: int
    samples: list[ReplaySample]
    outcome: float
    mean_search_ms: float = 0.0


def pack_selfplay_games(games: list[SelfPlayGame]) -> dict[str, object]:
    samples = [sample for game in games for sample in game.samples]
    if not samples:
        raise ValueError("Cannot pack an empty self-play game batch")
    return {
        "payload": pack_samples(samples),
        "games_generated": int(len(games)),
        "positions_generated": int(len(samples)),
        "mean_search_ms": float(np.mean([game.mean_search_ms for game in games])) if games else 0.0,
        "mean_game_len": float(np.mean([len(game.samples) for game in games])) if games else 0.0,
    }


def generate_selfplay_games(
    *,
    adapter: AffineOpenSpielAdapter,
    search_engine: SearchEngine,
    num_games: int,
    seed: int,
    num_parallel_games: int = 8,
) -> list[SelfPlayGame]:
    random.seed(seed)
    games: list[SelfPlayGame] = []
    active: list[dict[str, Any]] = []
    next_episode_id = 0

    def _spawn() -> None:
        nonlocal next_episode_id
        active.append(
            {
                "episode_id": next_episode_id,
                "state": adapter.new_initial_state(),
                "rows": [],
                "search_ms": [],
                "pending_row": None,
            }
        )
        next_episode_id += 1

    while next_episode_id < int(num_games) and len(active) < max(int(num_parallel_games), 1):
        _spawn()

    while active:
        encoded_batch = [adapter.encode_state(slot["state"]) for slot in active]
        obs_batch = np.stack([encoded.obs for encoded in encoded_batch]).astype(np.float32, copy=False)
        legal_batch = np.stack([encoded.legal_mask for encoded in encoded_batch]).astype(np.float32, copy=False)
        started = time.perf_counter()
        result = search_engine.run(obs_batch, legal_batch, [slot["state"] for slot in active], mode="selfplay")
        per_game_ms = ((time.perf_counter() - started) * 1000.0) / float(max(len(active), 1))

        for index, slot in enumerate(active):
            encoded = encoded_batch[index]
            previous_row = slot.get("pending_row")
            if previous_row is not None:
                previous_row["next_policy_target"] = result.root_policy[index].copy()
                previous_row["next_value_player"] = int(encoded.current_player)
                previous_row["recurrent_mask"] = 1.0
                slot["rows"].append(previous_row)
            action = int(result.chosen_action[index])
            next_state = slot["state"].clone()
            adapter.apply_dense_action(next_state, action)
            next_encoded = adapter.encode_state(next_state)
            reward_target = adapter.current_player_reward(slot["state"], next_state, encoded.current_player)
            current_row = {
                "obs": encoded.obs.copy(),
                "legal_mask": encoded.legal_mask.copy(),
                "policy_target": result.root_policy[index].copy(),
                "phase": encoded.phase,
                "move_index": encoded.move_index,
                "player": int(encoded.current_player),
                "action": action,
                "next_obs": next_encoded.obs.copy(),
                "next_legal_mask": next_encoded.legal_mask.copy(),
                "next_policy_target": np.zeros((adapter.spec.action_dim,), dtype=np.float32),
                "next_value_player": None,
                "recurrent_mask": 0.0,
                "reward_target": float(reward_target),
            }
            slot["search_ms"].append(per_game_ms)
            slot["state"] = next_state
            if next_encoded.terminal:
                slot["rows"].append(current_row)
                slot["pending_row"] = None
            else:
                slot["pending_row"] = current_row

        for slot in list(active):
            if not slot["state"].is_terminal():
                continue
            final_returns = slot["state"].returns()
            samples = []
            for row in slot["rows"]:
                player = int(row["player"])
                final_outcome = float(final_returns[player])
                next_value_target = 0.0
                if float(row["recurrent_mask"]) > 0.0 and row["next_value_player"] is not None:
                    next_value_target = float(final_returns[int(row["next_value_player"])])
                samples.append(
                    ReplaySample(
                        obs=row["obs"],
                        legal_mask=row["legal_mask"],
                        action=int(row["action"]),
                        next_obs=row["next_obs"],
                        next_legal_mask=row["next_legal_mask"],
                        next_policy_target=row["next_policy_target"],
                        next_value_target=float(next_value_target),
                        recurrent_mask=float(row["recurrent_mask"]),
                        policy_target=row["policy_target"],
                        value_target=float(final_outcome),
                        reward_target=float(row["reward_target"]),
                        phase=float(row["phase"]),
                        move_index=int(row["move_index"]),
                        variant_id=adapter.spec.variant_index,
                        weight_version=0,
                    )
                )
            games.append(
                SelfPlayGame(
                    episode_id=int(slot["episode_id"]),
                    samples=samples,
                    outcome=float(final_returns[0]),
                    mean_search_ms=float(np.mean(slot["search_ms"])) if slot["search_ms"] else 0.0,
                )
            )
            active.remove(slot)
            if next_episode_id < int(num_games):
                _spawn()
    return games


def selfplay_actor_process_main(
    *,
    config_path: str,
    worker_id: int,
    seed: int,
    num_parallel_games: int,
    games_per_chunk: int,
    output_queue,
    control_queue,
    inference_request_queue,
    inference_response_queue,
) -> None:
    config = load_yaml_config(config_path)
    adapter = AffineOpenSpielAdapter(resolve_spec_from_config(config))
    inference_client = BrokeredInferenceClient(
        worker_id=worker_id,
        request_queue=inference_request_queue,
        response_queue=inference_response_queue,
    )
    search = build_search_engine(
        model=None,
        inference_client=inference_client,
        adapter=adapter,
        config=config,
        device="cpu",
        seed=seed + worker_id * 10_000,
    )
    chunk_index = 0
    pending_stop = False

    def _drain_control_messages() -> None:
        nonlocal pending_stop
        while True:
            try:
                message = control_queue.get_nowait()
            except queue.Empty:
                return
            command = str(message.get("type", ""))
            if command == "stop":
                pending_stop = True
                return

    try:
        while not pending_stop:
            _drain_control_messages()
            if pending_stop:
                break
            games = generate_selfplay_games(
                adapter=adapter,
                search_engine=search,
                num_games=max(int(games_per_chunk), 1),
                seed=seed + worker_id * 100_000 + chunk_index * 1_000,
                num_parallel_games=num_parallel_games,
            )
            chunk = pack_selfplay_games(games)
            chunk.update(
                {
                    "type": "games",
                    "worker_id": int(worker_id),
                    "chunk_index": int(chunk_index),
                }
            )
            while not pending_stop:
                _drain_control_messages()
                if pending_stop:
                    break
                try:
                    output_queue.put(chunk, timeout=1.0)
                    break
                except queue.Full:
                    continue
            chunk_index += 1
    except Exception as exc:
        try:
            output_queue.put(
                {
                    "type": "error",
                    "worker_id": int(worker_id),
                    "error": repr(exc),
                },
                timeout=1.0,
            )
        except Exception:
            pass
        raise
