from __future__ import annotations

from dataclasses import dataclass
import itertools
import math
import multiprocessing as mp
import queue
import time
from typing import Any

import numpy as np
import torch

from projects.openspiel_muzero_pt.config_utils import (
    build_model_from_config,
    default_device,
    load_checkpoint,
    load_yaml_config,
    resolve_spec_from_config,
    save_checkpoint,
)
from projects.openspiel_muzero_pt.pipelines.learner import OnlineLearner
from projects.openspiel_muzero_pt.runtime.shared_memory import InferenceWorkerSharedBuffers


@dataclass(frozen=True, slots=True)
class GpuCoordinatorConfig:
    snapshot_sync_interval: int = 2000
    initial_max_batch_items: int = 4096
    recurrent_max_batch_items: int = 8192
    initial_max_wait_ms: float = 1.0
    recurrent_max_wait_ms: float = 1.0
    train_microbatch_size: int = 1024
    max_train_microbatches_per_turn: int = 2
    inference_low_watermark: int = 32


class BrokeredTrainClient:
    def __init__(self, *, request_queue, response_queue):
        self.request_queue = request_queue
        self.response_queue = response_queue
        self._request_ids = itertools.count()

    def _roundtrip(self, kind: str, **payload: Any) -> dict[str, Any]:
        request_id = int(next(self._request_ids))
        self.request_queue.put({"request_id": request_id, "kind": kind, "payload": payload})
        while True:
            response = self.response_queue.get()
            if int(response.get("request_id", -1)) != request_id:
                continue
            if str(response.get("status", "ok")) != "ok":
                raise RuntimeError(f"Train request failed: {response.get('error')}")
            return response["payload"]

    def train_batch(self, batch: dict[str, np.ndarray]) -> dict[str, float]:
        return self._roundtrip("train_batch", batch=batch)

    def save_checkpoint(self, *, path: str, step: int, metrics: dict[str, float] | None = None, include_optimizer: bool = True) -> None:
        self._roundtrip(
            "save_checkpoint",
            path=path,
            step=int(step),
            metrics=dict(metrics or {}),
            include_optimizer=bool(include_optimizer),
        )

    def stop(self) -> None:
        self._roundtrip("stop")


def _queue_wait_seconds(wait_ms: float) -> float:
    return max(float(wait_ms) / 1000.0, 1e-4)


def _gather_inference_requests(
    request_queue,
    pending: dict[str, list],
    *,
    first_request: dict[str, Any],
    max_items: int,
    max_wait_ms: float,
) -> list[dict[str, Any]]:
    requests = [first_request]
    items = int(first_request["batch_size"])
    started = time.perf_counter()
    target_kind = str(first_request.get("kind", ""))
    while items < max_items:
        # Drain pending local buffer for this kind first (no FeedData latency)
        if pending[target_kind]:
            candidate = pending[target_kind].pop(0)
        else:
            remaining = _queue_wait_seconds(max_wait_ms) - (time.perf_counter() - started)
            if remaining <= 0:
                break
            try:
                candidate = request_queue.get(timeout=remaining)
            except queue.Empty:
                break
            if str(candidate.get("kind", "")) != target_kind:
                # Wrong kind: stash locally, do NOT re-queue (avoids FeedData latency race)
                pending[str(candidate.get("kind", ""))].append(candidate)
                break
        candidate_items = int(candidate["batch_size"])
        if items + candidate_items > max_items and requests:
            # Too large to batch together: return to front of local buffer
            pending[target_kind].insert(0, candidate)
            break
        requests.append(candidate)
        items += candidate_items
    return requests


def _safe_qsize(queue_obj) -> int:
    try:
        return int(queue_obj.qsize())
    except (NotImplementedError, AttributeError):
        return 0


def _gpu_coordinator_main(
    *,
    config_path: str,
    init_checkpoint: str,
    device: str,
    inference_request_queue,
    train_request_queue,
    inference_response_queues: list[Any],
    inference_buffers_meta: list[dict[str, Any]],
    train_response_queue,
    coordinator_config: GpuCoordinatorConfig,
) -> None:
    torch.set_num_threads(1)
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        pass
    config = load_yaml_config(config_path)
    train_model, adapter = build_model_from_config(config)
    search_model, _ = build_model_from_config(config)
    device_obj = default_device(device)
    train_model.to(device_obj)
    search_model.to(device_obj)
    optimizer_cfg = dict(config.get("optimizer", {}))
    optimizer = torch.optim.AdamW(
        train_model.parameters(),
        lr=float(optimizer_cfg.get("lr_online", 5.0e-4)),
        weight_decay=float(optimizer_cfg.get("weight_decay", 1.0e-4)),
    )
    # --- Cosine LR schedule with linear warmup ---
    lr_base = float(optimizer_cfg.get("lr_online", 5.0e-4))
    lr_warmup_steps = int(optimizer_cfg.get("lr_warmup_steps", 1000))
    lr_min_ratio = float(optimizer_cfg.get("lr_min_ratio", 0.1))
    lr_min = lr_base * lr_min_ratio
    train_cfg = dict(config.get("train", {}))
    lr_total_steps = int(train_cfg.get("learner_steps_online", 2_000_000))

    def _compute_lr(current_step: int) -> float:
        if current_step < lr_warmup_steps:
            return lr_base * max(current_step, 1) / lr_warmup_steps
        progress = (current_step - lr_warmup_steps) / max(lr_total_steps - lr_warmup_steps, 1)
        progress = min(progress, 1.0)
        return lr_min + (lr_base - lr_min) * 0.5 * (1.0 + math.cos(math.pi * progress))

    if init_checkpoint:
        load_checkpoint(init_checkpoint, model=train_model)
    search_model.load_state_dict(train_model.state_dict())
    search_model.eval()
    learner = OnlineLearner(model=train_model, adapter=adapter, optimizer=optimizer, device=device_obj)
    inference_buffers = [InferenceWorkerSharedBuffers.attach(meta) for meta in inference_buffers_meta]
    step = 0
    stopped = False
    # Local in-memory buffer for requests pulled from queue but not yet matched to the
    # current serving kind.  Re-queuing via multiprocessing.Queue.put() would route
    # through the FeedData daemon thread, which may not be scheduled within wait_ms on
    # a busy node (70+ torch threads), causing permanent starvation of one inbox kind.
    _pending: dict[str, list] = {"initial": [], "recurrent": []}

    while not stopped:
        handled_inference = False
        for kind, max_items, wait_ms in (
            ("recurrent", coordinator_config.recurrent_max_batch_items, coordinator_config.recurrent_max_wait_ms),
            ("initial", coordinator_config.initial_max_batch_items, coordinator_config.initial_max_wait_ms),
        ):
            # Serve from local pending buffer first — zero FeedData overhead
            if _pending[kind]:
                first = _pending[kind].pop(0)
            else:
                try:
                    first = inference_request_queue.get(timeout=_queue_wait_seconds(wait_ms))
                except queue.Empty:
                    continue
                if str(first.get("kind", "")) != kind:
                    # Stash locally (not back to queue) to avoid FeedData thread race
                    _pending[str(first.get("kind", ""))].append(first)
                    continue
            requests = _gather_inference_requests(
                inference_request_queue,
                _pending,
                first_request=first,
                max_items=max_items,
                max_wait_ms=wait_ms,
            )
            if kind == "initial":
                obs = np.concatenate(
                    [
                        inference_buffers[int(request["worker_id"])].read_initial_request(int(request["batch_size"]))
                        for request in requests
                    ],
                    axis=0,
                )
                with torch.no_grad():
                    output = search_model.initial_inference(torch.from_numpy(obs).to(device_obj))
                payload = {
                    "latent": output.latent.detach().cpu().numpy().astype(np.float32, copy=False),
                    "policy_logits": output.policy_logits.detach().cpu().numpy().astype(np.float32, copy=False),
                    "value": output.value.detach().cpu().numpy().astype(np.float32, copy=False),
                }
            else:
                latent_batches = []
                action_plane_batches = []
                for request in requests:
                    latent_batch, action_batch = inference_buffers[int(request["worker_id"])].read_recurrent_request(
                        int(request["batch_size"])
                    )
                    latent_batches.append(latent_batch)
                    action_plane_batches.append(action_batch)
                latent = np.concatenate(latent_batches, axis=0)
                action_planes = np.concatenate(action_plane_batches, axis=0)
                with torch.no_grad():
                    output = search_model.recurrent_inference(
                        torch.from_numpy(latent).to(device_obj),
                        torch.from_numpy(action_planes).to(device_obj),
                    )
                payload = {
                    "latent": output.latent.detach().cpu().numpy().astype(np.float32, copy=False),
                    "reward": output.reward.detach().cpu().numpy().astype(np.float32, copy=False),
                    "policy_logits": output.policy_logits.detach().cpu().numpy().astype(np.float32, copy=False),
                    "value": output.value.detach().cpu().numpy().astype(np.float32, copy=False),
                }

            offset = 0
            for request in requests:
                worker_id = int(request["worker_id"])
                batch_size = int(request["batch_size"])
                response_payload = {key: value[offset : offset + batch_size] for key, value in payload.items()}
                worker_buffers = inference_buffers[worker_id]
                if kind == "initial":
                    worker_buffers.write_initial_response(
                        latent=response_payload["latent"],
                        policy_logits=response_payload["policy_logits"],
                        value=response_payload["value"],
                        batch_size=batch_size,
                    )
                else:
                    worker_buffers.write_recurrent_response(
                        latent=response_payload["latent"],
                        reward=response_payload["reward"],
                        policy_logits=response_payload["policy_logits"],
                        value=response_payload["value"],
                        batch_size=batch_size,
                    )
                inference_response_queues[int(request["worker_id"])].put(
                    {
                        "request_id": int(request["request_id"]),
                        "status": "ok",
                        "kind": kind,
                        "batch_size": batch_size,
                    }
                )
                offset += batch_size
            handled_inference = True
            break

        if handled_inference:
            if _safe_qsize(inference_request_queue) > max(coordinator_config.inference_low_watermark, 0):
                continue
            if not train_request_queue.empty():
                pass
            else:
                continue

        processed_train = 0
        while processed_train < max(int(coordinator_config.max_train_microbatches_per_turn), 1):
            if _safe_qsize(inference_request_queue) > max(coordinator_config.inference_low_watermark, 0):
                break
            try:
                request = train_request_queue.get(timeout=0.01 if processed_train == 0 else 0.0)
            except queue.Empty:
                break
            request_id = int(request.get("request_id", -1))
            kind = str(request.get("kind", ""))
            payload = dict(request.get("payload", {}))
            try:
                if kind == "train_batch":
                    metrics = learner.train_batch(
                        payload["batch"],
                        microbatch_size=int(coordinator_config.train_microbatch_size),
                    )
                    step += 1
                    # Apply cosine LR schedule with warmup
                    new_lr = _compute_lr(step)
                    for param_group in optimizer.param_groups:
                        param_group["lr"] = new_lr
                    if step % max(coordinator_config.snapshot_sync_interval, 1) == 0:
                        search_model.load_state_dict(train_model.state_dict())
                        search_model.eval()
                    train_response_queue.put(
                        {
                            "request_id": request_id,
                            "status": "ok",
                            "payload": {
                                "loss": metrics.loss,
                                "policy_loss": metrics.policy_loss,
                                "value_loss": metrics.value_loss,
                                "reward_loss": metrics.reward_loss,
                                "recurrent_policy_loss": metrics.recurrent_policy_loss,
                                "recurrent_value_loss": metrics.recurrent_value_loss,
                                "latent_loss": metrics.latent_loss,
                                "step": step,
                                "lr": new_lr,
                            },
                        }
                    )
                    processed_train += 1
                    continue
                if kind == "save_checkpoint":
                    save_checkpoint(
                        payload["path"],
                        model=train_model,
                        optimizer=optimizer if bool(payload.get("include_optimizer", True)) else None,
                        step=int(payload.get("step", step)),
                        metrics=dict(payload.get("metrics", {})),
                    )
                    train_response_queue.put({"request_id": request_id, "status": "ok", "payload": {}})
                    processed_train += 1
                    continue
                if kind == "stop":
                    train_response_queue.put({"request_id": request_id, "status": "ok", "payload": {}})
                    stopped = True
                    break
                train_response_queue.put(
                    {
                        "request_id": request_id,
                        "status": "error",
                        "error": f"Unsupported coordinator request kind: {kind}",
                        "payload": {},
                    }
                )
                processed_train += 1
            except Exception as exc:
                train_response_queue.put(
                    {
                        "request_id": request_id,
                        "status": "error",
                        "error": repr(exc),
                        "payload": {},
                    }
                )
                raise

        if processed_train > 0 or stopped:
            continue
        time.sleep(0.001)


def start_gpu_coordinator(
    *,
    config_path: str,
    init_checkpoint: str,
    device: str,
    actor_workers: int,
    max_actor_batch_size: int,
    coordinator_config: GpuCoordinatorConfig | None = None,
):
    config = load_yaml_config(config_path)
    spec = resolve_spec_from_config(config)
    model_cfg = dict(config.get("model", {}))
    channels = int(model_cfg.get("channels", 128))
    worker_buffers = [
        InferenceWorkerSharedBuffers.create(
            max_batch_size=max(int(max_actor_batch_size), 1),
            obs_shape=(spec.input_channels, spec.pad_h, spec.pad_w),
            latent_shape=(channels, spec.pad_h, spec.pad_w),
            action_planes_shape=(3, spec.pad_h, spec.pad_w),
            action_dim=spec.action_dim,
        )
        for _ in range(actor_workers)
    ]
    ctx = mp.get_context("spawn")
    inference_request_queue = ctx.Queue(maxsize=max(actor_workers * 4, 16))
    train_request_queue = ctx.Queue(maxsize=8)
    inference_response_queues = [ctx.Queue(maxsize=8) for _ in range(actor_workers)]
    train_response_queue = ctx.Queue(maxsize=8)
    process = ctx.Process(
        target=_gpu_coordinator_main,
        kwargs={
            "config_path": config_path,
            "init_checkpoint": init_checkpoint,
            "device": device,
            "inference_request_queue": inference_request_queue,
            "train_request_queue": train_request_queue,
            "inference_response_queues": inference_response_queues,
            "inference_buffers_meta": [worker_buffer.export() for worker_buffer in worker_buffers],
            "train_response_queue": train_response_queue,
            "coordinator_config": coordinator_config or GpuCoordinatorConfig(),
        },
        daemon=True,
    )
    process.start()
    return {
        "process": process,
        "inference_request_queue": inference_request_queue,
        "train_request_queue": train_request_queue,
        "inference_response_queues": inference_response_queues,
        "inference_buffer_metas": [worker_buffer.export() for worker_buffer in worker_buffers],
        "inference_worker_buffers": worker_buffers,
        "train_response_queue": train_response_queue,
    }
