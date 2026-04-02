from __future__ import annotations

from dataclasses import dataclass
import itertools
import multiprocessing as mp
import queue
import time
from typing import Any

import numpy as np
import torch

from projects.openspiel_muzero_pt.config_utils import build_model_from_config, default_device, load_checkpoint, load_yaml_config, save_checkpoint
from projects.openspiel_muzero_pt.pipelines.learner import OnlineLearner


@dataclass(frozen=True, slots=True)
class GpuCoordinatorConfig:
    snapshot_sync_interval: int = 2000
    initial_max_batch_items: int = 4096
    recurrent_max_batch_items: int = 8192
    initial_max_wait_ms: float = 1.0
    recurrent_max_wait_ms: float = 1.0


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
    *,
    first_request: dict[str, Any],
    max_items: int,
    max_wait_ms: float,
) -> list[dict[str, Any]]:
    requests = [first_request]
    items = int(first_request["payload"][next(iter(first_request["payload"]))].shape[0])
    started = time.perf_counter()
    while items < max_items:
        remaining = _queue_wait_seconds(max_wait_ms) - (time.perf_counter() - started)
        if remaining <= 0:
            break
        try:
            candidate = request_queue.get(timeout=remaining)
        except queue.Empty:
            break
        if str(candidate.get("kind", "")) != str(first_request.get("kind", "")):
            request_queue.put(candidate)
            break
        candidate_items = int(candidate["payload"][next(iter(candidate["payload"]))].shape[0])
        if items + candidate_items > max_items and requests:
            request_queue.put(candidate)
            break
        requests.append(candidate)
        items += candidate_items
    return requests


def _gpu_coordinator_main(
    *,
    config_path: str,
    init_checkpoint: str,
    device: str,
    inference_request_queue,
    train_request_queue,
    inference_response_queues: list[Any],
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
    if init_checkpoint:
        load_checkpoint(init_checkpoint, model=train_model)
    search_model.load_state_dict(train_model.state_dict())
    search_model.eval()
    learner = OnlineLearner(model=train_model, adapter=adapter, optimizer=optimizer, device=device_obj)
    step = 0
    stopped = False

    while not stopped:
        handled_inference = False
        for kind, max_items, wait_ms in (
            ("recurrent", coordinator_config.recurrent_max_batch_items, coordinator_config.recurrent_max_wait_ms),
            ("initial", coordinator_config.initial_max_batch_items, coordinator_config.initial_max_wait_ms),
        ):
            try:
                first = inference_request_queue.get(timeout=_queue_wait_seconds(wait_ms))
            except queue.Empty:
                continue
            if str(first.get("kind", "")) != kind:
                inference_request_queue.put(first)
                continue
            requests = _gather_inference_requests(
                inference_request_queue,
                first_request=first,
                max_items=max_items,
                max_wait_ms=wait_ms,
            )
            if kind == "initial":
                obs = np.concatenate([request["payload"]["obs"] for request in requests], axis=0)
                with torch.no_grad():
                    output = search_model.initial_inference(torch.from_numpy(obs).to(device_obj))
                payload = {
                    "latent": output.latent.detach().cpu().numpy().astype(np.float32, copy=False),
                    "policy_logits": output.policy_logits.detach().cpu().numpy().astype(np.float32, copy=False),
                    "value": output.value.detach().cpu().numpy().astype(np.float32, copy=False),
                }
            else:
                latent = np.concatenate([request["payload"]["latent"] for request in requests], axis=0)
                action_planes = np.concatenate([request["payload"]["action_planes"] for request in requests], axis=0)
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
                batch_size = int(request["payload"][next(iter(request["payload"]))].shape[0])
                response_payload = {key: value[offset : offset + batch_size].copy() for key, value in payload.items()}
                inference_response_queues[int(request["worker_id"])].put(
                    {
                        "request_id": int(request["request_id"]),
                        "status": "ok",
                        "payload": response_payload,
                    }
                )
                offset += batch_size
            handled_inference = True
            break

        if handled_inference:
            continue

        try:
            request = train_request_queue.get(timeout=0.01)
        except queue.Empty:
            continue
        request_id = int(request.get("request_id", -1))
        kind = str(request.get("kind", ""))
        payload = dict(request.get("payload", {}))
        try:
            if kind == "train_batch":
                metrics = learner.train_batch(payload["batch"])
                step += 1
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
                        },
                    }
                )
            elif kind == "save_checkpoint":
                save_checkpoint(
                    payload["path"],
                    model=train_model,
                    optimizer=optimizer if bool(payload.get("include_optimizer", True)) else None,
                    step=int(payload.get("step", step)),
                    metrics=dict(payload.get("metrics", {})),
                )
                train_response_queue.put({"request_id": request_id, "status": "ok", "payload": {}})
            elif kind == "stop":
                train_response_queue.put({"request_id": request_id, "status": "ok", "payload": {}})
                stopped = True
            else:
                train_response_queue.put(
                    {
                        "request_id": request_id,
                        "status": "error",
                        "error": f"Unsupported coordinator request kind: {kind}",
                        "payload": {},
                    }
                )
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


def start_gpu_coordinator(
    *,
    config_path: str,
    init_checkpoint: str,
    device: str,
    actor_workers: int,
    coordinator_config: GpuCoordinatorConfig | None = None,
):
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
        "train_response_queue": train_response_queue,
    }
