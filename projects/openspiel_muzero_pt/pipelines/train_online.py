from __future__ import annotations

import argparse
import json
import multiprocessing as mp
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import time

import numpy as np

from projects.openspiel_muzero_pt.config_utils import (
    default_device,
    load_yaml_config,
    resolve_spec_from_config,
)
from projects.openspiel_muzero_pt.pipelines.selfplay_actor import selfplay_actor_process_main
from projects.openspiel_muzero_pt.replay.expert_buffer import ExpertBuffer
from projects.openspiel_muzero_pt.replay.ring_buffer import ArrayRingBuffer
from projects.openspiel_muzero_pt.runtime.gpu_coordinator import BrokeredTrainClient, GpuCoordinatorConfig, start_gpu_coordinator
from projects.openspiel_muzero_pt.runtime.shared_memory import ReplayChunkSharedBuffers
from projects.openspiel_muzero_pt.runtime.settings import (
    parse_actor_runtime_settings,
    parse_gpu_coordinator_runtime_settings,
    parse_online_loop_settings,
)
from projects.openspiel_muzero_pt.utils import JsonProgressWriter, JsonlEventWriter, append_event, eta_seconds, utc_now


def _merge_batches(expert_batch: dict[str, np.ndarray], live_batch: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    return {key: np.concatenate([expert_batch[key], live_batch[key]], axis=0) for key in expert_batch}


def _launch_quick_eval_process(
    *,
    config_path: str,
    checkpoint_path: str,
    device: str,
    seed: int,
    quick_games: int,
    quick_num_workers: int,
    output_path: str,
    log_path: str,
) -> tuple[subprocess.Popen[str], object]:
    cmd = [
        sys.executable,
        "-m",
        "projects.openspiel_muzero_pt.pipelines.evaluate_vs_affine_mcts",
        "--mode",
        "quick",
        "--config",
        config_path,
        "--checkpoint",
        checkpoint_path,
        "--games",
        str(int(quick_games)),
        "--num-workers",
        str(int(quick_num_workers)),
        "--device",
        device,
        "--output",
        output_path,
        "--seed",
        str(int(seed)),
    ]
    log_handle = Path(log_path).open("a", encoding="utf-8")
    process = subprocess.Popen(
        cmd,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    return process, log_handle


def _safe_queue_size(queue_obj) -> int | None:
    try:
        return int(queue_obj.qsize())
    except (NotImplementedError, AttributeError):
        return None


def _update_convergence_state(
    *,
    report: dict[str, object],
    quick_threshold: float,
    required_games: int,
    required_passes: int,
    current_streak: int,
) -> tuple[bool, int, bool]:
    games_completed = int(report.get("games_completed", report.get("games", 0)) or 0)
    win_rate = float(report.get("win_rate", report.get("current_win_rate", 0.0)) or 0.0)
    passed = games_completed >= int(required_games) and win_rate > float(quick_threshold)
    streak = current_streak + 1 if passed else 0
    converged = streak >= int(required_passes)
    return passed, streak, converged


def _resolve_replay_batch_sizes(
    *,
    batch_size: int,
    replay_ratio: dict[str, object] | None,
    expert_available: bool,
) -> tuple[int, int]:
    batch_size = max(int(batch_size), 1)
    if not expert_available:
        return batch_size, 0
    ratio_cfg = dict(replay_ratio or {})
    live_weight = max(float(ratio_cfg.get("live", 1.0)), 0.0)
    expert_weight = max(float(ratio_cfg.get("expert", 1.0)), 0.0)
    if live_weight <= 0.0 and expert_weight <= 0.0:
        live_weight = 1.0
        expert_weight = 1.0
    if live_weight <= 0.0:
        return 0, batch_size
    if expert_weight <= 0.0:
        return batch_size, 0
    total_weight = live_weight + expert_weight
    live_batch_size = int(round(batch_size * (live_weight / total_weight)))
    if batch_size >= 2:
        live_batch_size = min(max(live_batch_size, 1), batch_size - 1)
    else:
        live_batch_size = 1
    expert_batch_size = batch_size - live_batch_size
    return live_batch_size, expert_batch_size


def _policy_entropy(policy_target: np.ndarray) -> np.ndarray:
    clipped = np.clip(np.asarray(policy_target, dtype=np.float32), 1.0e-8, None)
    return -(np.asarray(policy_target, dtype=np.float32) * np.log(clipped)).sum(axis=1)


def _summarize_batch_targets(
    batch: dict[str, np.ndarray] | None,
    *,
    sample_limit: int = 4,
) -> dict[str, object] | None:
    if batch is None or not batch:
        return None
    rows = int(batch["action"].shape[0])
    legal_count = np.asarray(batch["legal_mask"], dtype=np.float32).sum(axis=1)
    entropy = _policy_entropy(batch["policy_target"])
    value_target = np.asarray(batch["value_target"], dtype=np.float32)
    reward_target = np.asarray(batch["reward_target"], dtype=np.float32)
    sample_rows = []
    for index in range(min(rows, int(sample_limit))):
        sample_rows.append(
            {
                "row_index": int(index),
                "policy_entropy": float(entropy[index]),
                "value_target": float(value_target[index]),
                "reward_target": float(reward_target[index]),
                "legal_count": int(legal_count[index]),
                "chosen_action": int(batch["action"][index]),
            }
        )
    return {
        "rows": rows,
        "policy_entropy_mean": float(entropy.mean()) if rows else 0.0,
        "policy_entropy_std": float(entropy.std()) if rows else 0.0,
        "value_target_mean": float(value_target.mean()) if rows else 0.0,
        "value_target_std": float(value_target.std()) if rows else 0.0,
        "reward_target_mean": float(reward_target.mean()) if rows else 0.0,
        "reward_target_std": float(reward_target.std()) if rows else 0.0,
        "legal_count_mean": float(legal_count.mean()) if rows else 0.0,
        "sample_rows": sample_rows,
    }


def _result_slot_rows_capacity(*, max_game_length: int, active_games_per_actor: int, chunk_flush_positions: int, chunk_flush_games: int) -> int:
    estimated_max_game_rows = max(int(max_game_length), 1)
    base_rows = max(
        int(chunk_flush_positions),
        int(chunk_flush_games) * estimated_max_game_rows,
        estimated_max_game_rows,
    )
    overshoot_rows = max(int(active_games_per_actor), 1) * estimated_max_game_rows
    return max(base_rows + overshoot_rows, estimated_max_game_rows)


def run_online_training(
    *,
    config_path: str,
    init_checkpoint: str,
    output_dir: str,
    expert_dir: str | None = None,
    device: str | None = None,
    seed: int = 0,
) -> dict[str, float | int | str | bool | None]:
    config = load_yaml_config(config_path)
    device_obj = default_device(device)
    expert_payload = ExpertBuffer.from_dir(expert_dir).load_all() if expert_dir else None
    rng = np.random.default_rng(seed)

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    progress_writer = JsonProgressWriter(output_root / "online.progress.json")
    event_writer = JsonlEventWriter(output_root / "online.events.jsonl")
    started_at = time.time()

    train_cfg = dict(config.get("train", {}))
    eval_cfg = dict(config.get("eval", {}))
    buffers_cfg = dict(config.get("buffers", {}))
    online_settings = parse_online_loop_settings(config)
    actor_settings = parse_actor_runtime_settings(config)
    coordinator_settings = parse_gpu_coordinator_runtime_settings(config)
    spec = resolve_spec_from_config(config)
    batch_size = online_settings.batch_size
    total_steps = online_settings.total_steps
    eval_interval = online_settings.eval_interval
    checkpoint_interval = online_settings.checkpoint_interval
    log_interval = online_settings.log_interval
    active_games_per_actor = actor_settings.active_games_per_actor
    chunk_flush_games = actor_settings.chunk_flush_games
    chunk_flush_positions = actor_settings.chunk_flush_positions
    if chunk_flush_positions <= 0:
        chunk_flush_positions = max(chunk_flush_games * int(spec.max_game_length), int(spec.max_game_length))
    chunk_flush_seconds = actor_settings.chunk_flush_seconds
    actor_workers = actor_settings.workers
    actor_queue_size = actor_settings.result_queue_size
    result_queue_slots = actor_settings.result_queue_slots
    live_capacity = int(buffers_cfg.get("live_capacity", 2_000_000))
    quick_games = int(eval_cfg.get("quick_games", eval_cfg.get("quick_gate_games", 200)))
    quick_num_workers = int(eval_cfg.get("quick_num_workers", 4))
    quick_threshold = float(eval_cfg.get("quick_threshold_for_official", eval_cfg.get("acceptance_target_winrate", 0.90)))
    convergence_games = max(int(eval_cfg.get("convergence_games", quick_games)), 1)
    convergence_required_passes = max(int(eval_cfg.get("convergence_consecutive_passes", 2)), 1)
    auto_official_eval = online_settings.auto_official_eval
    stop_on_convergence = bool(train_cfg.get("stop_on_convergence", True))
    live_batch_size, expert_batch_size = _resolve_replay_batch_sizes(
        batch_size=batch_size,
        replay_ratio=dict(train_cfg.get("replay_ratio", {})),
        expert_available=expert_payload is not None,
    )
    recency_bias = float(train_cfg.get("recency_bias", 0.0))
    # Expert ratio decay: gradually shift from expert → live data
    expert_decay_steps = int(train_cfg.get("expert_decay_steps", 0))
    expert_min_ratio = float(train_cfg.get("expert_min_ratio", 0.1))
    initial_expert_frac = expert_batch_size / max(batch_size, 1) if batch_size > 0 else 0.0

    replay_buffer = ArrayRingBuffer(capacity=live_capacity)
    best_quick_win_rate = -1.0
    official_ready = False
    convergence_pass_streak = 0
    converged = False
    last_report: dict[str, float | int | str | bool | None] = {}
    pending_eval: subprocess.Popen[str] | None = None
    pending_eval_log_handle = None
    pending_eval_snapshot: Path | None = None
    latest_checkpoint_path = output_root / "latest.pt"
    best_checkpoint_path = output_root / "best.pt"
    quick_eval_output_path = output_root / "quick_eval.json"
    quick_eval_log_path = output_root / "quick_eval.process.log"
    actor_ctx = mp.get_context("spawn")
    actor_result_queue = actor_ctx.Queue(maxsize=actor_queue_size)
    actor_control_queues = [actor_ctx.Queue() for _ in range(actor_workers)]
    actor_result_slot_queues = [actor_ctx.Queue(maxsize=result_queue_slots) for _ in range(actor_workers)]
    actor_processes: list[mp.Process] = []
    worker_heartbeats: dict[int, dict[str, float | int]] = {}
    live_rows_appended_since_last_log = 0
    last_logged_replay_rows = 0
    last_logged_selfplay_games = 0
    result_buffers = [
        ReplayChunkSharedBuffers.create(
            slot_count=result_queue_slots,
            max_rows_per_slot=_result_slot_rows_capacity(
                max_game_length=spec.max_game_length,
                active_games_per_actor=active_games_per_actor,
                chunk_flush_positions=chunk_flush_positions,
                chunk_flush_games=chunk_flush_games,
            ),
            obs_shape=(spec.input_channels, spec.pad_h, spec.pad_w),
            action_dim=spec.action_dim,
        )
        for _ in range(actor_workers)
    ]
    for slot_queue in actor_result_slot_queues:
        for slot_id in range(result_queue_slots):
            slot_queue.put(slot_id)
    coordinator = start_gpu_coordinator(
        config_path=config_path,
        init_checkpoint=init_checkpoint,
        device=str(device_obj),
        actor_workers=actor_workers,
        max_actor_batch_size=active_games_per_actor,
        coordinator_config=GpuCoordinatorConfig(
            snapshot_sync_interval=coordinator_settings.snapshot_sync_interval,
            initial_max_batch_items=coordinator_settings.initial_max_batch_items,
            recurrent_max_batch_items=coordinator_settings.recurrent_max_batch_items,
            initial_max_wait_ms=coordinator_settings.initial_max_wait_ms,
            recurrent_max_wait_ms=coordinator_settings.recurrent_max_wait_ms,
            train_microbatch_size=coordinator_settings.train_microbatch_size,
            max_train_microbatches_per_turn=coordinator_settings.max_train_microbatches_per_turn,
            inference_low_watermark=coordinator_settings.inference_low_watermark,
        ),
    )
    train_client = BrokeredTrainClient(
        request_queue=coordinator["train_request_queue"],
        response_queue=coordinator["train_response_queue"],
    )

    progress_payload: dict[str, float | int | str | bool | None] = {
        "ts": utc_now(),
        "status": "running",
        "phase": "online",
        "step": 0,
        "steps_total": total_steps,
        "device": str(device_obj),
        "replay_rows": 0,
        "selfplay_games_completed": 0,
        "latest_checkpoint_path": "",
        "best_checkpoint_path": "",
        "last_eval_win_rate": None,
        "best_quick_win_rate": None,
        "official_ready": False,
        "official_skipped_reason": "quick threshold not met",
        "actor_workers": actor_workers,
        "parallel_games_per_actor": active_games_per_actor,
        "active_games_per_actor": active_games_per_actor,
        "chunk_flush_positions": chunk_flush_positions,
        "chunk_flush_games": chunk_flush_games,
        "chunk_flush_seconds": chunk_flush_seconds,
        "live_queue_depth": 0,
        "live_batch_size": live_batch_size,
        "expert_batch_size": expert_batch_size,
        "replay_rows_delta_since_last_log": 0,
        "selfplay_games_delta_since_last_log": 0,
        "unique_replay_rows_seen_recently_proxy": 0,
        "staged_ready_rows": 0,
        "pending_rows_in_active_slots": 0,
        "staged_terminal_rows": 0,
        "oldest_active_game_age_sec_max": 0.0,
        "mean_active_game_length_so_far_mean": 0.0,
        "actor_checkpoint_path": str(init_checkpoint),
        "convergence_games": convergence_games,
        "convergence_consecutive_passes_required": convergence_required_passes,
        "convergence_pass_streak": 0,
        "converged": False,
        "estimated_remaining_seconds": None,
    }
    progress_writer.write(progress_payload)

    def _refresh_actor_diagnostics() -> None:
        if not worker_heartbeats:
            progress_payload["staged_ready_rows"] = 0
            progress_payload["pending_rows_in_active_slots"] = 0
            progress_payload["staged_terminal_rows"] = 0
            progress_payload["oldest_active_game_age_sec_max"] = 0.0
            progress_payload["mean_active_game_length_so_far_mean"] = 0.0
            return
        progress_payload["staged_ready_rows"] = int(
            sum(int(heartbeat.get("staged_ready_rows", 0)) for heartbeat in worker_heartbeats.values())
        )
        progress_payload["pending_rows_in_active_slots"] = int(
            sum(int(heartbeat.get("pending_rows_in_active_slots", 0)) for heartbeat in worker_heartbeats.values())
        )
        progress_payload["staged_terminal_rows"] = int(
            sum(int(heartbeat.get("staged_terminal_rows", 0)) for heartbeat in worker_heartbeats.values())
        )
        progress_payload["oldest_active_game_age_sec_max"] = float(
            max(float(heartbeat.get("oldest_active_game_age_sec", 0.0)) for heartbeat in worker_heartbeats.values())
        )
        progress_payload["mean_active_game_length_so_far_mean"] = float(
            np.mean([float(heartbeat.get("mean_active_game_length_so_far", 0.0)) for heartbeat in worker_heartbeats.values()])
        )

    def _start_actors() -> None:
        for worker_id, control_queue in enumerate(actor_control_queues):
            process = actor_ctx.Process(
                target=selfplay_actor_process_main,
                kwargs={
                    "config_path": config_path,
                    "worker_id": worker_id,
                    "seed": seed,
                    "active_games_per_actor": active_games_per_actor,
                    "chunk_flush_positions": chunk_flush_positions,
                    "chunk_flush_games": chunk_flush_games,
                    "chunk_flush_seconds": chunk_flush_seconds,
                    "output_queue": actor_result_queue,
                    "control_queue": control_queue,
                    "result_slot_queue": actor_result_slot_queues[worker_id],
                    "result_buffers_meta": result_buffers[worker_id].export(),
                    "inference_request_queue": coordinator["inference_request_queue"],
                    "inference_response_queue": coordinator["inference_response_queues"][worker_id],
                    "inference_buffers_meta": coordinator["inference_buffer_metas"][worker_id],
                },
                daemon=True,
            )
            process.start()
            actor_processes.append(process)
            append_event(
                event_writer,
                kind="actor_started",
                worker_id=worker_id,
                pid=int(process.pid or -1),
                checkpoint_path=str(init_checkpoint),
            )

    def _drain_actor_queue(*, block: bool = False) -> None:
        nonlocal live_rows_appended_since_last_log
        drained_any = False
        while True:
            timeout = 30.0 if block and not drained_any else 0.0
            try:
                item = actor_result_queue.get(timeout=timeout)
            except queue.Empty:
                break
            drained_any = True
            if str(item.get("type", "")) == "error":
                raise RuntimeError(f"Self-play actor {item.get('worker_id')} failed: {item.get('error')}")
            if str(item.get("type", "")) == "actor_heartbeat":
                worker_id = int(item["worker_id"])
                worker_heartbeats[worker_id] = {
                    "active_slots": int(item.get("active_slots", 0)),
                    "completed_games_since_last_flush": int(item.get("completed_games_since_last_flush", 0)),
                    "staged_ready_rows": int(item.get("staged_ready_rows", 0)),
                    "pending_rows_in_active_slots": int(item.get("pending_rows_in_active_slots", 0)),
                    "staged_terminal_rows": int(item.get("staged_terminal_rows", 0)),
                    "oldest_active_game_age_sec": float(item.get("oldest_active_game_age_sec", 0.0)),
                    "mean_active_game_length_so_far": float(item.get("mean_active_game_length_so_far", 0.0)),
                }
                _refresh_actor_diagnostics()
                append_event(
                    event_writer,
                    kind="actor_heartbeat",
                    worker_id=worker_id,
                    **worker_heartbeats[worker_id],
                )
                continue
            if str(item.get("type", "")) != "games_descriptor":
                continue
            worker_id = int(item["worker_id"])
            slot_id = int(item["slot_id"])
            rows = int(item["rows"])
            replay_buffer.append_chunk(result_buffers[worker_id].read_slot(slot_id, rows))
            live_rows_appended_since_last_log += rows
            actor_result_slot_queues[worker_id].put(slot_id)
            progress_payload["selfplay_games_completed"] = int(progress_payload["selfplay_games_completed"]) + int(
                item["games_generated"]
            )
            append_event(
                event_writer,
                kind="selfplay_chunk",
                worker_id=worker_id,
                slot_id=slot_id,
                games_generated=int(item["games_generated"]),
                positions_generated=int(item["positions_generated"]),
                mean_search_ms=float(item["mean_search_ms"]),
                mean_game_len=float(item["mean_game_len"]),
                active_slots=int(item.get("active_slots", -1)),
                flush_reason=str(item.get("flush_reason", "")),
            )
            _refresh_actor_diagnostics()
        queue_depth = _safe_queue_size(actor_result_queue)
        progress_payload["live_queue_depth"] = queue_depth if queue_depth is not None else -1

    def _harvest_eval_future() -> None:
        nonlocal pending_eval, pending_eval_snapshot, best_quick_win_rate, official_ready, last_report
        nonlocal pending_eval_log_handle
        nonlocal convergence_pass_streak, converged
        if pending_eval is None:
            return
        return_code = pending_eval.poll()
        if return_code is None:
            return
        if pending_eval_log_handle is not None:
            pending_eval_log_handle.close()
            pending_eval_log_handle = None
        if return_code != 0:
            append_event(
                event_writer,
                kind="quick_eval_failed",
                checkpoint_path=str(pending_eval_snapshot) if pending_eval_snapshot else "",
                return_code=return_code,
                log_path=str(quick_eval_log_path),
            )
            progress_payload["ts"] = utc_now()
            progress_writer.write(progress_payload)
            pending_eval = None
            pending_eval_snapshot = None
            return
        if not quick_eval_output_path.exists():
            append_event(
                event_writer,
                kind="quick_eval_missing_output",
                checkpoint_path=str(pending_eval_snapshot) if pending_eval_snapshot else "",
                output_path=str(quick_eval_output_path),
            )
            pending_eval = None
            pending_eval_snapshot = None
            return
        report = json.loads(quick_eval_output_path.read_text(encoding="utf-8"))
        win_rate = float(report["win_rate"])
        last_report.update(report)
        progress_payload["last_eval_win_rate"] = win_rate
        progress_payload["best_quick_win_rate"] = max(float(progress_payload.get("best_quick_win_rate") or -1.0), win_rate)
        if win_rate >= best_quick_win_rate:
            best_quick_win_rate = win_rate
            if pending_eval_snapshot is not None and pending_eval_snapshot.exists():
                shutil.copy2(pending_eval_snapshot, best_checkpoint_path)
                progress_payload["best_checkpoint_path"] = str(best_checkpoint_path)
        official_ready = win_rate >= quick_threshold
        passed_gate, convergence_pass_streak, converged = _update_convergence_state(
            report=report,
            quick_threshold=quick_threshold,
            required_games=convergence_games,
            required_passes=convergence_required_passes,
            current_streak=convergence_pass_streak,
        )
        progress_payload["official_ready"] = official_ready
        progress_payload["official_skipped_reason"] = None if official_ready else "quick threshold not met"
        progress_payload["convergence_pass_streak"] = convergence_pass_streak
        progress_payload["converged"] = converged
        progress_payload["ts"] = utc_now()
        progress_writer.write(progress_payload)
        append_event(
            event_writer,
            kind="quick_eval_complete",
            step=report.get("step"),
            win_rate=win_rate,
            official_ready=official_ready,
            passed_convergence_gate=passed_gate,
            convergence_pass_streak=convergence_pass_streak,
            converged=converged,
            checkpoint_path=str(pending_eval_snapshot) if pending_eval_snapshot else "",
        )
        pending_eval = None
        pending_eval_snapshot = None

    try:
        _start_actors()
        completed_steps = 0
        for step in range(1, total_steps + 1):
            _harvest_eval_future()
            if stop_on_convergence and converged:
                break
            required_live_rows = max(live_batch_size, 1) if live_batch_size > 0 else 0
            while required_live_rows > 0 and len(replay_buffer) < required_live_rows:
                _drain_actor_queue(block=True)
            _drain_actor_queue(block=False)

            live_batch = replay_buffer.sample_batch(live_batch_size, rng=rng, recency_bias=recency_bias) if live_batch_size > 0 else None
            expert_batch = None
            if expert_payload is not None and expert_batch_size > 0:
                # Decay expert ratio over time
                effective_expert_bs = expert_batch_size
                if expert_decay_steps > 0 and initial_expert_frac > expert_min_ratio:
                    progress = min(step / expert_decay_steps, 1.0)
                    effective_frac = initial_expert_frac * (1.0 - progress) + expert_min_ratio * progress
                    effective_expert_bs = max(int(round(batch_size * effective_frac)), 1)
                    live_batch_size_eff = batch_size - effective_expert_bs
                    if live_batch is None and live_batch_size_eff > 0 and len(replay_buffer) >= live_batch_size_eff:
                        live_batch = replay_buffer.sample_batch(live_batch_size_eff, rng=rng, recency_bias=recency_bias)
                    elif live_batch is not None and live_batch_size_eff != live_batch_size:
                        live_batch = replay_buffer.sample_batch(live_batch_size_eff, rng=rng, recency_bias=recency_bias)
                expert_index = rng.integers(0, expert_payload["action"].shape[0], size=effective_expert_bs)
                expert_batch = {key: value[expert_index] for key, value in expert_payload.items()}
                batch = _merge_batches(expert_batch, live_batch) if live_batch is not None else expert_batch
            else:
                batch = live_batch
            if batch is None:
                raise RuntimeError("Online training could not construct a batch from live or expert replay")
            metrics = train_client.train_batch(batch)
            last_report = {
                "step": step,
                "loss": float(metrics["loss"]),
                "policy_loss": float(metrics["policy_loss"]),
                "value_loss": float(metrics["value_loss"]),
                "reward_loss": float(metrics["reward_loss"]),
                "lr": float(metrics.get("lr", 0.0)),
            }
            progress_payload.update(
                {
                    "ts": utc_now(),
                    "step": step,
                    "loss": float(metrics["loss"]),
                    "policy_loss": float(metrics["policy_loss"]),
                    "value_loss": float(metrics["value_loss"]),
                    "reward_loss": float(metrics["reward_loss"]),
                    "replay_rows": len(replay_buffer),
                    "live_batch_size": live_batch_size,
                    "expert_batch_size": expert_batch_size,
                    "estimated_remaining_seconds": eta_seconds(started_at=started_at, completed=step, total=total_steps),
                }
            )
            if step % checkpoint_interval == 0 or step == total_steps:
                train_client.save_checkpoint(path=str(latest_checkpoint_path), step=step, metrics=last_report)
                progress_payload["latest_checkpoint_path"] = str(latest_checkpoint_path)
            if step % eval_interval == 0 or step == total_steps:
                if pending_eval is None:
                    eval_snapshot = output_root / f"eval_step_{step}.pt"
                    train_client.save_checkpoint(path=str(eval_snapshot), step=step, metrics=last_report)
                    pending_eval_snapshot = eval_snapshot
                    pending_eval, pending_eval_log_handle = _launch_quick_eval_process(
                        config_path=config_path,
                        checkpoint_path=str(eval_snapshot),
                        device=str(device_obj),
                        seed=seed + step,
                        quick_games=quick_games,
                        quick_num_workers=quick_num_workers,
                        output_path=str(quick_eval_output_path),
                        log_path=str(quick_eval_log_path),
                    )
                    append_event(
                        event_writer,
                        kind="quick_eval_submitted",
                        step=step,
                        checkpoint_path=str(eval_snapshot),
                        quick_games=quick_games,
                        quick_num_workers=quick_num_workers,
                        pid=int(pending_eval.pid),
                    )
                else:
                    append_event(
                        event_writer,
                        kind="quick_eval_skipped_busy",
                        step=step,
                        reason="background quick eval still running",
                    )
            if step % log_interval == 0 or step == total_steps:
                replay_rows_delta_since_last_log = int(len(replay_buffer) - last_logged_replay_rows)
                selfplay_games_delta_since_last_log = int(progress_payload["selfplay_games_completed"]) - int(last_logged_selfplay_games)
                progress_payload["replay_rows_delta_since_last_log"] = replay_rows_delta_since_last_log
                progress_payload["selfplay_games_delta_since_last_log"] = selfplay_games_delta_since_last_log
                progress_payload["unique_replay_rows_seen_recently_proxy"] = int(live_rows_appended_since_last_log)
                progress_writer.write(progress_payload)
                append_event(
                        event_writer,
                        kind="train_log",
                        step=step,
                        loss=float(metrics["loss"]),
                        replay_rows=len(replay_buffer),
                        live_queue_depth=progress_payload["live_queue_depth"],
                        selfplay_games_completed=progress_payload["selfplay_games_completed"],
                        last_eval_win_rate=progress_payload["last_eval_win_rate"],
                        live_batch_size=live_batch_size,
                        expert_batch_size=expert_batch_size,
                        replay_rows_delta_since_last_log=replay_rows_delta_since_last_log,
                        selfplay_games_delta_since_last_log=selfplay_games_delta_since_last_log,
                        unique_replay_rows_seen_recently_proxy=int(live_rows_appended_since_last_log),
                        staged_ready_rows=progress_payload["staged_ready_rows"],
                        pending_rows_in_active_slots=progress_payload["pending_rows_in_active_slots"],
                        staged_terminal_rows=progress_payload["staged_terminal_rows"],
                        oldest_active_game_age_sec_max=progress_payload["oldest_active_game_age_sec_max"],
                        mean_active_game_length_so_far_mean=progress_payload["mean_active_game_length_so_far_mean"],
                        inference_request_depth=_safe_queue_size(coordinator["inference_request_queue"]),
                        train_request_depth=_safe_queue_size(coordinator["train_request_queue"]),
                    )
                append_event(
                    event_writer,
                    kind="batch_diagnostics",
                    step=step,
                    live_batch_size=live_batch_size,
                    expert_batch_size=expert_batch_size,
                    live_batch=_summarize_batch_targets(live_batch),
                    expert_batch=_summarize_batch_targets(expert_batch),
                )
                last_logged_replay_rows = len(replay_buffer)
                last_logged_selfplay_games = int(progress_payload["selfplay_games_completed"])
                live_rows_appended_since_last_log = 0
            completed_steps = step

        if pending_eval is not None:
            pending_eval.wait()
            _harvest_eval_future()
        if auto_official_eval and official_ready:
            progress_payload["official_skipped_reason"] = "official auto-run not implemented in v1"
        progress_payload.update(
            {
                "ts": utc_now(),
                "status": "completed",
                "phase": "online",
                "step": completed_steps,
                "best_quick_win_rate": best_quick_win_rate if best_quick_win_rate >= 0 else None,
                "official_ready": official_ready,
                "convergence_pass_streak": convergence_pass_streak,
                "converged": converged,
                "estimated_remaining_seconds": 0.0,
            }
        )
        progress_writer.write(progress_payload)
        append_event(
            event_writer,
            kind="online_complete",
            step=completed_steps,
            best_quick_win_rate=progress_payload["best_quick_win_rate"],
            official_ready=official_ready,
            converged=converged,
        )
        return {**last_report, **progress_payload}
    finally:
        for control_queue in actor_control_queues:
            try:
                control_queue.put({"type": "stop"})
            except Exception:
                pass
        for process in actor_processes:
            process.join(timeout=5.0)
            if process.is_alive():
                process.terminate()
        try:
            actor_result_queue.close()
        except Exception:
            pass
        try:
            train_client.stop()
        except Exception:
            pass
        coordinator["process"].join(timeout=5.0)
        if coordinator["process"].is_alive():
            coordinator["process"].terminate()
        for worker_buffers in coordinator["inference_worker_buffers"]:
            try:
                worker_buffers.close()
            except Exception:
                pass
            try:
                worker_buffers.unlink()
            except Exception:
                pass
        for result_buffer in result_buffers:
            try:
                result_buffer.close()
            except Exception:
                pass
            try:
                result_buffer.unlink()
            except Exception:
                pass
        if pending_eval_log_handle is not None:
            pending_eval_log_handle.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the single-GPU Affine OpenSpiel online training loop")
    parser.add_argument("--config", required=True)
    parser.add_argument("--init", required=True)
    parser.add_argument("--expert", default="")
    parser.add_argument("--out", default="artifacts/openspiel_muzero_pt/online")
    parser.add_argument("--device", default="")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    Path(args.out).mkdir(parents=True, exist_ok=True)
    report = run_online_training(
        config_path=args.config,
        init_checkpoint=args.init,
        output_dir=args.out,
        expert_dir=args.expert or None,
        device=args.device or None,
        seed=args.seed,
    )
    report_path = Path(args.out) / "online_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
