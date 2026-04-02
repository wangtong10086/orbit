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
from projects.openspiel_muzero_pt.runtime.shared_memory import ReplayChunkSharedBuffers
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


def should_flush_selfplay_chunk(
    *,
    staged_positions: int,
    staged_games: int,
    last_flush_at: float,
    now: float,
    flush_positions: int,
    flush_games: int,
    flush_seconds: float,
) -> str | None:
    if staged_positions <= 0:
        return None
    if flush_positions > 0 and staged_positions >= flush_positions:
        return "positions"
    if flush_games > 0 and staged_games >= flush_games:
        return "games"
    if flush_seconds > 0.0 and (now - last_flush_at) >= flush_seconds:
        return "time"
    return None


def _spawn_slot(adapter: AffineOpenSpielAdapter, episode_id: int) -> dict[str, Any]:
    return {
        "episode_id": int(episode_id),
        "state": adapter.new_initial_state(),
        "encoded": None,
        "root_node": None,
        "rows": [],
        "search_ms": [],
        "pending_row": None,
    }


def _finalize_completed_game(adapter: AffineOpenSpielAdapter, slot: dict[str, Any]) -> SelfPlayGame:
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
    return SelfPlayGame(
        episode_id=int(slot["episode_id"]),
        samples=samples,
        outcome=float(final_returns[0]),
        mean_search_ms=float(np.mean(slot["search_ms"])) if slot["search_ms"] else 0.0,
    )


def _advance_selfplay_slots(
    *,
    adapter: AffineOpenSpielAdapter,
    search_engine: SearchEngine,
    active: list[dict[str, Any]],
) -> list[SelfPlayGame]:
    if not active:
        return []
    encoded_batch = []
    for slot in active:
        encoded = slot.get("encoded")
        if encoded is None:
            encoded = adapter.encode_state(slot["state"])
            slot["encoded"] = encoded
        encoded_batch.append(encoded)
    obs_batch = np.stack([encoded.obs for encoded in encoded_batch]).astype(np.float32, copy=False)
    legal_batch = np.stack([encoded.legal_mask for encoded in encoded_batch]).astype(np.float32, copy=False)
    started = time.perf_counter()
    result = search_engine.run(
        obs_batch,
        legal_batch,
        [slot["state"] for slot in active],
        mode="selfplay",
        encoded_state_batch=encoded_batch,
        root_nodes=[slot.get("root_node") for slot in active],
    )
    per_game_ms = ((time.perf_counter() - started) * 1000.0) / float(max(len(active), 1))

    completed_games: list[SelfPlayGame] = []
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
        slot["root_node"] = search_engine.promote_child_root(
            root=result.root_nodes[index],
            action=action,
            next_state=next_state,
        )
        slot["state"] = next_state
        slot["encoded"] = next_encoded if not next_encoded.terminal else None
        if next_encoded.terminal:
            slot["rows"].append(current_row)
            slot["pending_row"] = None
            slot["root_node"] = None
            completed_games.append(_finalize_completed_game(adapter, slot))
        else:
            slot["pending_row"] = current_row

    active[:] = [slot for slot in active if not slot["state"].is_terminal()]
    return completed_games


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

    while len(games) < int(num_games):
        while next_episode_id < int(num_games) and len(active) < max(int(num_parallel_games), 1):
            active.append(_spawn_slot(adapter, next_episode_id))
            next_episode_id += 1
        games.extend(_advance_selfplay_slots(adapter=adapter, search_engine=search_engine, active=active))
    return games[: int(num_games)]


def selfplay_actor_process_main(
    *,
    config_path: str,
    worker_id: int,
    seed: int,
    active_games_per_actor: int,
    chunk_flush_positions: int,
    chunk_flush_games: int,
    chunk_flush_seconds: float,
    output_queue,
    control_queue,
    result_slot_queue,
    result_buffers_meta,
    inference_request_queue,
    inference_response_queue,
    inference_buffers_meta,
) -> None:
    config = load_yaml_config(config_path)
    adapter = AffineOpenSpielAdapter(resolve_spec_from_config(config))
    inference_client = BrokeredInferenceClient(
        worker_id=worker_id,
        request_queue=inference_request_queue,
        response_queue=inference_response_queue,
        shared_buffers_meta=inference_buffers_meta,
    )
    result_buffers = ReplayChunkSharedBuffers.attach(result_buffers_meta)
    search = build_search_engine(
        model=None,
        inference_client=inference_client,
        adapter=adapter,
        config=config,
        device="cpu",
        seed=seed + worker_id * 10_000,
    )
    active: list[dict[str, Any]] = []
    staged_games: list[SelfPlayGame] = []
    staged_positions = 0
    next_episode_id = 0
    pending_stop = False
    last_flush_at = time.monotonic()

    def _drain_control_messages() -> None:
        nonlocal pending_stop
        while True:
            try:
                message = control_queue.get_nowait()
            except queue.Empty:
                return
            if str(message.get("type", "")) == "stop":
                pending_stop = True
                return

    def _flush_staged(flush_reason: str) -> bool:
        nonlocal staged_games, staged_positions, last_flush_at
        if not staged_games:
            return False
        packed = pack_selfplay_games(staged_games)
        while not pending_stop:
            _drain_control_messages()
            if pending_stop:
                break
            try:
                slot_id = int(result_slot_queue.get(timeout=1.0))
                break
            except queue.Empty:
                continue
        else:
            return False
        if pending_stop:
            return False
        rows = result_buffers.write_slot(slot_id, packed["payload"])
        descriptor = {
            "type": "games_descriptor",
            "worker_id": int(worker_id),
            "slot_id": int(slot_id),
            "rows": int(rows),
            "games_generated": int(packed["games_generated"]),
            "positions_generated": int(packed["positions_generated"]),
            "mean_search_ms": float(packed["mean_search_ms"]),
            "mean_game_len": float(packed["mean_game_len"]),
            "active_slots": int(len(active)),
            "flush_reason": str(flush_reason),
        }
        while not pending_stop:
            _drain_control_messages()
            if pending_stop:
                break
            try:
                output_queue.put(descriptor, timeout=1.0)
                staged_games = []
                staged_positions = 0
                last_flush_at = time.monotonic()
                return True
            except queue.Full:
                continue
        try:
            result_slot_queue.put(slot_id, timeout=1.0)
        except Exception:
            pass
        return False

    try:
        while not pending_stop:
            _drain_control_messages()
            while not pending_stop and len(active) < max(int(active_games_per_actor), 1):
                active.append(_spawn_slot(adapter, next_episode_id))
                next_episode_id += 1
            if pending_stop:
                break
            completed_games = _advance_selfplay_slots(adapter=adapter, search_engine=search, active=active)
            if completed_games:
                staged_games.extend(completed_games)
                staged_positions += int(sum(len(game.samples) for game in completed_games))
            flush_reason = should_flush_selfplay_chunk(
                staged_positions=staged_positions,
                staged_games=len(staged_games),
                last_flush_at=last_flush_at,
                now=time.monotonic(),
                flush_positions=int(chunk_flush_positions),
                flush_games=int(chunk_flush_games),
                flush_seconds=float(chunk_flush_seconds),
            )
            if flush_reason is not None:
                _flush_staged(flush_reason)
        if staged_games:
            _flush_staged("shutdown")
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
    finally:
        result_buffers.close()
