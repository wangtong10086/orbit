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
)
from projects.openspiel_muzero_pt.pipelines.selfplay_actor import selfplay_actor_process_main
from projects.openspiel_muzero_pt.replay.expert_buffer import ExpertBuffer
from projects.openspiel_muzero_pt.replay.ring_buffer import ArrayRingBuffer
from projects.openspiel_muzero_pt.runtime.gpu_coordinator import BrokeredTrainClient, GpuCoordinatorConfig, start_gpu_coordinator
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
    batch_size = online_settings.batch_size
    total_steps = online_settings.total_steps
    eval_interval = online_settings.eval_interval
    checkpoint_interval = online_settings.checkpoint_interval
    log_interval = online_settings.log_interval
    parallel_games = actor_settings.parallel_games_per_actor
    actor_workers = actor_settings.workers
    games_per_chunk = actor_settings.games_per_chunk
    actor_queue_size = actor_settings.result_queue_size
    live_capacity = int(buffers_cfg.get("live_capacity", 2_000_000))
    quick_games = int(eval_cfg.get("quick_games", eval_cfg.get("quick_gate_games", 200)))
    quick_num_workers = int(eval_cfg.get("quick_num_workers", 4))
    quick_threshold = float(eval_cfg.get("quick_threshold_for_official", eval_cfg.get("acceptance_target_winrate", 0.90)))
    auto_official_eval = online_settings.auto_official_eval

    replay_buffer = ArrayRingBuffer(capacity=live_capacity)
    best_quick_win_rate = -1.0
    official_ready = False
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
    actor_processes: list[mp.Process] = []
    coordinator = start_gpu_coordinator(
        config_path=config_path,
        init_checkpoint=init_checkpoint,
        device=str(device_obj),
        actor_workers=actor_workers,
        coordinator_config=GpuCoordinatorConfig(
            snapshot_sync_interval=coordinator_settings.snapshot_sync_interval,
            initial_max_batch_items=coordinator_settings.initial_max_batch_items,
            recurrent_max_batch_items=coordinator_settings.recurrent_max_batch_items,
            initial_max_wait_ms=coordinator_settings.initial_max_wait_ms,
            recurrent_max_wait_ms=coordinator_settings.recurrent_max_wait_ms,
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
        "parallel_games_per_actor": parallel_games,
        "actor_games_per_chunk": games_per_chunk,
        "live_queue_depth": 0,
        "actor_checkpoint_path": str(init_checkpoint),
        "estimated_remaining_seconds": None,
    }
    progress_writer.write(progress_payload)

    def _start_actors() -> None:
        for worker_id, control_queue in enumerate(actor_control_queues):
            process = actor_ctx.Process(
                target=selfplay_actor_process_main,
                kwargs={
                    "config_path": config_path,
                    "worker_id": worker_id,
                    "seed": seed,
                    "num_parallel_games": parallel_games,
                    "games_per_chunk": games_per_chunk,
                    "output_queue": actor_result_queue,
                    "control_queue": control_queue,
                    "inference_request_queue": coordinator["inference_request_queue"],
                    "inference_response_queue": coordinator["inference_response_queues"][worker_id],
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
            if str(item.get("type", "")) != "games":
                continue
            replay_buffer.append_chunk(item["payload"])
            progress_payload["selfplay_games_completed"] = int(progress_payload["selfplay_games_completed"]) + int(
                item["games_generated"]
            )
            append_event(
                event_writer,
                kind="selfplay_chunk",
                worker_id=int(item["worker_id"]),
                chunk_index=int(item["chunk_index"]),
                games_generated=int(item["games_generated"]),
                positions_generated=int(item["positions_generated"]),
                mean_search_ms=float(item["mean_search_ms"]),
                mean_game_len=float(item["mean_game_len"]),
            )
        queue_depth = _safe_queue_size(actor_result_queue)
        progress_payload["live_queue_depth"] = queue_depth if queue_depth is not None else -1

    def _harvest_eval_future() -> None:
        nonlocal pending_eval, pending_eval_snapshot, best_quick_win_rate, official_ready, last_report
        nonlocal pending_eval_log_handle
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
        progress_payload["official_ready"] = official_ready
        progress_payload["official_skipped_reason"] = None if official_ready else "quick threshold not met"
        progress_payload["ts"] = utc_now()
        progress_writer.write(progress_payload)
        append_event(
            event_writer,
            kind="quick_eval_complete",
            step=report.get("step"),
            win_rate=win_rate,
            official_ready=official_ready,
            checkpoint_path=str(pending_eval_snapshot) if pending_eval_snapshot else "",
        )
        pending_eval = None
        pending_eval_snapshot = None

    try:
        _start_actors()
        for step in range(1, total_steps + 1):
            _harvest_eval_future()
            while len(replay_buffer) < batch_size:
                _drain_actor_queue(block=True)
            _drain_actor_queue(block=False)

            live_batch_size = max(batch_size // 2, 1)
            live_batch = replay_buffer.sample_batch(live_batch_size, rng=rng)
            if expert_payload is not None:
                expert_index = rng.integers(0, expert_payload["action"].shape[0], size=max(batch_size - live_batch_size, 1))
                expert_batch = {key: value[expert_index] for key, value in expert_payload.items()}
                batch = _merge_batches(expert_batch, live_batch)
            else:
                batch = live_batch
            metrics = train_client.train_batch(batch)
            last_report = {
                "step": step,
                "loss": float(metrics["loss"]),
                "policy_loss": float(metrics["policy_loss"]),
                "value_loss": float(metrics["value_loss"]),
                "reward_loss": float(metrics["reward_loss"]),
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
                    )

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
                "step": total_steps,
                "best_quick_win_rate": best_quick_win_rate if best_quick_win_rate >= 0 else None,
                "official_ready": official_ready,
                "estimated_remaining_seconds": 0.0,
            }
        )
        progress_writer.write(progress_payload)
        append_event(
            event_writer,
            kind="online_complete",
            step=total_steps,
            best_quick_win_rate=progress_payload["best_quick_win_rate"],
            official_ready=official_ready,
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
        if pending_eval_log_handle is not None:
            pending_eval_log_handle.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the single-GPU Othello online training loop")
    parser.add_argument("--config", required=True)
    parser.add_argument("--init", required=True)
    parser.add_argument("--expert", default="")
    parser.add_argument("--out", default="artifacts/openspiel_muzero_pt/othello_online")
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
