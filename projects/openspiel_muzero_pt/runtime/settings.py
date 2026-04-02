from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ActorRuntimeSettings:
    workers: int
    parallel_games_per_actor: int
    games_per_chunk: int
    result_queue_size: int


@dataclass(frozen=True, slots=True)
class GpuCoordinatorRuntimeSettings:
    snapshot_sync_interval: int
    initial_max_batch_items: int
    recurrent_max_batch_items: int
    initial_max_wait_ms: float
    recurrent_max_wait_ms: float


@dataclass(frozen=True, slots=True)
class OnlineLoopSettings:
    batch_size: int
    total_steps: int
    eval_interval: int
    checkpoint_interval: int
    log_interval: int
    auto_official_eval: bool


def _section(config: dict[str, Any], key: str) -> dict[str, Any]:
    value = config.get(key, {})
    return dict(value) if isinstance(value, dict) else {}


def parse_actor_runtime_settings(config: dict[str, Any]) -> ActorRuntimeSettings:
    train_cfg = _section(config, "train")
    actor_cfg = _section(config, "actors")
    workers = max(int(actor_cfg.get("workers", train_cfg.get("actor_workers", 1))), 1)
    parallel_games = max(int(actor_cfg.get("parallel_games_per_actor", train_cfg.get("parallel_games_per_actor", 8))), 1)
    games_per_chunk = max(int(actor_cfg.get("games_per_chunk", train_cfg.get("actor_games_per_chunk", parallel_games))), 1)
    result_queue_size = max(int(actor_cfg.get("result_queue_size", train_cfg.get("actor_queue_size", workers * 2))), 1)
    return ActorRuntimeSettings(
        workers=workers,
        parallel_games_per_actor=parallel_games,
        games_per_chunk=games_per_chunk,
        result_queue_size=result_queue_size,
    )


def parse_gpu_coordinator_runtime_settings(config: dict[str, Any]) -> GpuCoordinatorRuntimeSettings:
    train_cfg = _section(config, "train")
    runtime_cfg = _section(config, "runtime")
    coordinator_cfg = dict(runtime_cfg.get("gpu_coordinator", {})) if isinstance(runtime_cfg.get("gpu_coordinator", {}), dict) else {}
    return GpuCoordinatorRuntimeSettings(
        snapshot_sync_interval=max(int(coordinator_cfg.get("snapshot_sync_interval", train_cfg.get("snapshot_sync_interval", 2000))), 1),
        initial_max_batch_items=max(int(coordinator_cfg.get("initial_max_batch_items", 4096)), 1),
        recurrent_max_batch_items=max(int(coordinator_cfg.get("recurrent_max_batch_items", 8192)), 1),
        initial_max_wait_ms=float(coordinator_cfg.get("initial_max_wait_ms", 1.0)),
        recurrent_max_wait_ms=float(coordinator_cfg.get("recurrent_max_wait_ms", 1.0)),
    )


def parse_online_loop_settings(config: dict[str, Any]) -> OnlineLoopSettings:
    train_cfg = _section(config, "train")
    total_steps = max(int(train_cfg.get("learner_steps_online", 100000)), 1)
    checkpoint_interval = max(int(train_cfg.get("checkpoint_interval", 1000)), 1)
    eval_interval = max(int(train_cfg.get("eval_interval", 2000)), 1)
    log_interval = max(int(train_cfg.get("log_interval", max(min(total_steps // 100, 100), 1))), 1)
    return OnlineLoopSettings(
        batch_size=max(int(train_cfg.get("batch_size_per_gpu", 512)), 1),
        total_steps=total_steps,
        eval_interval=eval_interval,
        checkpoint_interval=checkpoint_interval,
        log_interval=log_interval,
        auto_official_eval=bool(train_cfg.get("auto_official_eval", False)),
    )
