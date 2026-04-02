from __future__ import annotations

from dataclasses import dataclass
from multiprocessing import shared_memory
from typing import Any

import numpy as np


@dataclass(frozen=True, slots=True)
class SharedArrayMeta:
    name: str
    shape: tuple[int, ...]
    dtype: str


class SharedArray:
    def __init__(self, *, shm: shared_memory.SharedMemory, shape: tuple[int, ...], dtype: np.dtype, owner: bool):
        self.shm = shm
        self.shape = tuple(int(dim) for dim in shape)
        self.dtype = np.dtype(dtype)
        self.owner = bool(owner)
        self.array = np.ndarray(self.shape, dtype=self.dtype, buffer=self.shm.buf)

    @classmethod
    def create(cls, *, shape: tuple[int, ...], dtype: np.dtype) -> "SharedArray":
        dtype = np.dtype(dtype)
        size_bytes = int(np.prod(shape, dtype=np.int64)) * int(dtype.itemsize)
        shm = shared_memory.SharedMemory(create=True, size=size_bytes)
        return cls(shm=shm, shape=shape, dtype=dtype, owner=True)

    @classmethod
    def attach(cls, meta: SharedArrayMeta | dict[str, Any]) -> "SharedArray":
        if isinstance(meta, dict):
            meta = SharedArrayMeta(
                name=str(meta["name"]),
                shape=tuple(int(dim) for dim in meta["shape"]),
                dtype=str(meta["dtype"]),
            )
        shm = shared_memory.SharedMemory(name=meta.name, create=False)
        return cls(shm=shm, shape=meta.shape, dtype=np.dtype(meta.dtype), owner=False)

    def export(self) -> dict[str, Any]:
        return {
            "name": self.shm.name,
            "shape": list(self.shape),
            "dtype": str(self.dtype),
        }

    def close(self) -> None:
        self.shm.close()

    def unlink(self) -> None:
        if self.owner:
            self.shm.unlink()


class InferenceWorkerSharedBuffers:
    def __init__(
        self,
        *,
        request_obs: SharedArray,
        request_latent: SharedArray,
        request_action_planes: SharedArray,
        response_latent: SharedArray,
        response_policy_logits: SharedArray,
        response_value: SharedArray,
        response_reward: SharedArray,
        max_batch_size: int,
    ):
        self.request_obs = request_obs
        self.request_latent = request_latent
        self.request_action_planes = request_action_planes
        self.response_latent = response_latent
        self.response_policy_logits = response_policy_logits
        self.response_value = response_value
        self.response_reward = response_reward
        self.max_batch_size = int(max_batch_size)

    @classmethod
    def create(
        cls,
        *,
        max_batch_size: int,
        obs_shape: tuple[int, ...],
        latent_shape: tuple[int, ...],
        action_planes_shape: tuple[int, ...],
        action_dim: int,
    ) -> "InferenceWorkerSharedBuffers":
        max_batch_size = max(int(max_batch_size), 1)
        return cls(
            request_obs=SharedArray.create(shape=(max_batch_size, *obs_shape), dtype=np.float32),
            request_latent=SharedArray.create(shape=(max_batch_size, *latent_shape), dtype=np.float32),
            request_action_planes=SharedArray.create(shape=(max_batch_size, *action_planes_shape), dtype=np.float32),
            response_latent=SharedArray.create(shape=(max_batch_size, *latent_shape), dtype=np.float32),
            response_policy_logits=SharedArray.create(shape=(max_batch_size, int(action_dim)), dtype=np.float32),
            response_value=SharedArray.create(shape=(max_batch_size,), dtype=np.float32),
            response_reward=SharedArray.create(shape=(max_batch_size,), dtype=np.float32),
            max_batch_size=max_batch_size,
        )

    @classmethod
    def attach(cls, meta: dict[str, Any]) -> "InferenceWorkerSharedBuffers":
        return cls(
            request_obs=SharedArray.attach(meta["request_obs"]),
            request_latent=SharedArray.attach(meta["request_latent"]),
            request_action_planes=SharedArray.attach(meta["request_action_planes"]),
            response_latent=SharedArray.attach(meta["response_latent"]),
            response_policy_logits=SharedArray.attach(meta["response_policy_logits"]),
            response_value=SharedArray.attach(meta["response_value"]),
            response_reward=SharedArray.attach(meta["response_reward"]),
            max_batch_size=int(meta["max_batch_size"]),
        )

    def export(self) -> dict[str, Any]:
        return {
            "request_obs": self.request_obs.export(),
            "request_latent": self.request_latent.export(),
            "request_action_planes": self.request_action_planes.export(),
            "response_latent": self.response_latent.export(),
            "response_policy_logits": self.response_policy_logits.export(),
            "response_value": self.response_value.export(),
            "response_reward": self.response_reward.export(),
            "max_batch_size": self.max_batch_size,
        }

    def write_initial_request(self, obs_batch: np.ndarray) -> int:
        obs_batch = np.asarray(obs_batch, dtype=np.float32)
        batch_size = int(obs_batch.shape[0])
        if batch_size > self.max_batch_size:
            raise ValueError(f"Initial request batch_size={batch_size} exceeds max_batch_size={self.max_batch_size}")
        self.request_obs.array[:batch_size] = obs_batch
        return batch_size

    def read_initial_request(self, batch_size: int) -> np.ndarray:
        return self.request_obs.array[: int(batch_size)]

    def write_recurrent_request(self, latent_batch: np.ndarray, action_planes_batch: np.ndarray) -> int:
        latent_batch = np.asarray(latent_batch, dtype=np.float32)
        action_planes_batch = np.asarray(action_planes_batch, dtype=np.float32)
        batch_size = int(latent_batch.shape[0])
        if batch_size > self.max_batch_size:
            raise ValueError(f"Recurrent request batch_size={batch_size} exceeds max_batch_size={self.max_batch_size}")
        self.request_latent.array[:batch_size] = latent_batch
        self.request_action_planes.array[:batch_size] = action_planes_batch
        return batch_size

    def read_recurrent_request(self, batch_size: int) -> tuple[np.ndarray, np.ndarray]:
        batch_size = int(batch_size)
        return self.request_latent.array[:batch_size], self.request_action_planes.array[:batch_size]

    def write_initial_response(self, *, latent: np.ndarray, policy_logits: np.ndarray, value: np.ndarray, batch_size: int) -> None:
        batch_size = int(batch_size)
        self.response_latent.array[:batch_size] = np.asarray(latent, dtype=np.float32)
        self.response_policy_logits.array[:batch_size] = np.asarray(policy_logits, dtype=np.float32)
        self.response_value.array[:batch_size] = np.asarray(value, dtype=np.float32)

    def read_initial_response(self, batch_size: int) -> dict[str, np.ndarray]:
        batch_size = int(batch_size)
        return {
            "latent": self.response_latent.array[:batch_size].copy(),
            "policy_logits": self.response_policy_logits.array[:batch_size].copy(),
            "value": self.response_value.array[:batch_size].copy(),
        }

    def write_recurrent_response(
        self,
        *,
        latent: np.ndarray,
        reward: np.ndarray,
        policy_logits: np.ndarray,
        value: np.ndarray,
        batch_size: int,
    ) -> None:
        batch_size = int(batch_size)
        self.response_latent.array[:batch_size] = np.asarray(latent, dtype=np.float32)
        self.response_reward.array[:batch_size] = np.asarray(reward, dtype=np.float32)
        self.response_policy_logits.array[:batch_size] = np.asarray(policy_logits, dtype=np.float32)
        self.response_value.array[:batch_size] = np.asarray(value, dtype=np.float32)

    def read_recurrent_response(self, batch_size: int) -> dict[str, np.ndarray]:
        batch_size = int(batch_size)
        return {
            "latent": self.response_latent.array[:batch_size].copy(),
            "reward": self.response_reward.array[:batch_size].copy(),
            "policy_logits": self.response_policy_logits.array[:batch_size].copy(),
            "value": self.response_value.array[:batch_size].copy(),
        }

    def close(self) -> None:
        for array in (
            self.request_obs,
            self.request_latent,
            self.request_action_planes,
            self.response_latent,
            self.response_policy_logits,
            self.response_value,
            self.response_reward,
        ):
            array.close()

    def unlink(self) -> None:
        for array in (
            self.request_obs,
            self.request_latent,
            self.request_action_planes,
            self.response_latent,
            self.response_policy_logits,
            self.response_value,
            self.response_reward,
        ):
            array.unlink()


class ReplayChunkSharedBuffers:
    def __init__(
        self,
        *,
        obs: SharedArray,
        legal_mask: SharedArray,
        action: SharedArray,
        next_obs: SharedArray,
        next_legal_mask: SharedArray,
        next_policy_target: SharedArray,
        next_value_target: SharedArray,
        recurrent_mask: SharedArray,
        policy_target: SharedArray,
        value_target: SharedArray,
        reward_target: SharedArray,
        phase: SharedArray,
        move_index: SharedArray,
        variant_id: SharedArray,
        weight_version: SharedArray,
        slot_count: int,
        max_rows_per_slot: int,
    ):
        self.obs = obs
        self.legal_mask = legal_mask
        self.action = action
        self.next_obs = next_obs
        self.next_legal_mask = next_legal_mask
        self.next_policy_target = next_policy_target
        self.next_value_target = next_value_target
        self.recurrent_mask = recurrent_mask
        self.policy_target = policy_target
        self.value_target = value_target
        self.reward_target = reward_target
        self.phase = phase
        self.move_index = move_index
        self.variant_id = variant_id
        self.weight_version = weight_version
        self.slot_count = int(slot_count)
        self.max_rows_per_slot = int(max_rows_per_slot)

    @classmethod
    def create(
        cls,
        *,
        slot_count: int,
        max_rows_per_slot: int,
        obs_shape: tuple[int, ...],
        action_dim: int,
    ) -> "ReplayChunkSharedBuffers":
        slot_count = max(int(slot_count), 1)
        max_rows_per_slot = max(int(max_rows_per_slot), 1)
        policy_shape = (slot_count, max_rows_per_slot, int(action_dim))
        obs_storage_shape = (slot_count, max_rows_per_slot, *obs_shape)
        scalar_f32_shape = (slot_count, max_rows_per_slot)
        scalar_i64_shape = (slot_count, max_rows_per_slot)
        return cls(
            obs=SharedArray.create(shape=obs_storage_shape, dtype=np.float32),
            legal_mask=SharedArray.create(shape=policy_shape, dtype=np.float32),
            action=SharedArray.create(shape=scalar_i64_shape, dtype=np.int64),
            next_obs=SharedArray.create(shape=obs_storage_shape, dtype=np.float32),
            next_legal_mask=SharedArray.create(shape=policy_shape, dtype=np.float32),
            next_policy_target=SharedArray.create(shape=policy_shape, dtype=np.float32),
            next_value_target=SharedArray.create(shape=scalar_f32_shape, dtype=np.float32),
            recurrent_mask=SharedArray.create(shape=scalar_f32_shape, dtype=np.float32),
            policy_target=SharedArray.create(shape=policy_shape, dtype=np.float32),
            value_target=SharedArray.create(shape=scalar_f32_shape, dtype=np.float32),
            reward_target=SharedArray.create(shape=scalar_f32_shape, dtype=np.float32),
            phase=SharedArray.create(shape=scalar_f32_shape, dtype=np.float32),
            move_index=SharedArray.create(shape=scalar_i64_shape, dtype=np.int64),
            variant_id=SharedArray.create(shape=scalar_i64_shape, dtype=np.int64),
            weight_version=SharedArray.create(shape=scalar_i64_shape, dtype=np.int64),
            slot_count=slot_count,
            max_rows_per_slot=max_rows_per_slot,
        )

    @classmethod
    def attach(cls, meta: dict[str, Any]) -> "ReplayChunkSharedBuffers":
        return cls(
            obs=SharedArray.attach(meta["obs"]),
            legal_mask=SharedArray.attach(meta["legal_mask"]),
            action=SharedArray.attach(meta["action"]),
            next_obs=SharedArray.attach(meta["next_obs"]),
            next_legal_mask=SharedArray.attach(meta["next_legal_mask"]),
            next_policy_target=SharedArray.attach(meta["next_policy_target"]),
            next_value_target=SharedArray.attach(meta["next_value_target"]),
            recurrent_mask=SharedArray.attach(meta["recurrent_mask"]),
            policy_target=SharedArray.attach(meta["policy_target"]),
            value_target=SharedArray.attach(meta["value_target"]),
            reward_target=SharedArray.attach(meta["reward_target"]),
            phase=SharedArray.attach(meta["phase"]),
            move_index=SharedArray.attach(meta["move_index"]),
            variant_id=SharedArray.attach(meta["variant_id"]),
            weight_version=SharedArray.attach(meta["weight_version"]),
            slot_count=int(meta["slot_count"]),
            max_rows_per_slot=int(meta["max_rows_per_slot"]),
        )

    def export(self) -> dict[str, Any]:
        return {
            "obs": self.obs.export(),
            "legal_mask": self.legal_mask.export(),
            "action": self.action.export(),
            "next_obs": self.next_obs.export(),
            "next_legal_mask": self.next_legal_mask.export(),
            "next_policy_target": self.next_policy_target.export(),
            "next_value_target": self.next_value_target.export(),
            "recurrent_mask": self.recurrent_mask.export(),
            "policy_target": self.policy_target.export(),
            "value_target": self.value_target.export(),
            "reward_target": self.reward_target.export(),
            "phase": self.phase.export(),
            "move_index": self.move_index.export(),
            "variant_id": self.variant_id.export(),
            "weight_version": self.weight_version.export(),
            "slot_count": self.slot_count,
            "max_rows_per_slot": self.max_rows_per_slot,
        }

    def write_slot(self, slot_id: int, payload: dict[str, np.ndarray]) -> int:
        slot_id = int(slot_id)
        rows = int(payload["action"].shape[0])
        if not (0 <= slot_id < self.slot_count):
            raise ValueError(f"slot_id {slot_id} outside [0, {self.slot_count})")
        if rows > self.max_rows_per_slot:
            raise ValueError(f"Replay payload rows={rows} exceed max_rows_per_slot={self.max_rows_per_slot}")
        self.obs.array[slot_id, :rows] = np.asarray(payload["obs"], dtype=np.float32)
        self.legal_mask.array[slot_id, :rows] = np.asarray(payload["legal_mask"], dtype=np.float32)
        self.action.array[slot_id, :rows] = np.asarray(payload["action"], dtype=np.int64)
        self.next_obs.array[slot_id, :rows] = np.asarray(payload["next_obs"], dtype=np.float32)
        self.next_legal_mask.array[slot_id, :rows] = np.asarray(payload["next_legal_mask"], dtype=np.float32)
        self.next_policy_target.array[slot_id, :rows] = np.asarray(payload["next_policy_target"], dtype=np.float32)
        self.next_value_target.array[slot_id, :rows] = np.asarray(payload["next_value_target"], dtype=np.float32)
        self.recurrent_mask.array[slot_id, :rows] = np.asarray(payload["recurrent_mask"], dtype=np.float32)
        self.policy_target.array[slot_id, :rows] = np.asarray(payload["policy_target"], dtype=np.float32)
        self.value_target.array[slot_id, :rows] = np.asarray(payload["value_target"], dtype=np.float32)
        self.reward_target.array[slot_id, :rows] = np.asarray(payload["reward_target"], dtype=np.float32)
        self.phase.array[slot_id, :rows] = np.asarray(payload["phase"], dtype=np.float32)
        self.move_index.array[slot_id, :rows] = np.asarray(payload["move_index"], dtype=np.int64)
        self.variant_id.array[slot_id, :rows] = np.asarray(payload["variant_id"], dtype=np.int64)
        self.weight_version.array[slot_id, :rows] = np.asarray(payload["weight_version"], dtype=np.int64)
        return rows

    def read_slot(self, slot_id: int, rows: int) -> dict[str, np.ndarray]:
        slot_id = int(slot_id)
        rows = int(rows)
        return {
            "obs": self.obs.array[slot_id, :rows].copy(),
            "legal_mask": self.legal_mask.array[slot_id, :rows].copy(),
            "action": self.action.array[slot_id, :rows].copy(),
            "next_obs": self.next_obs.array[slot_id, :rows].copy(),
            "next_legal_mask": self.next_legal_mask.array[slot_id, :rows].copy(),
            "next_policy_target": self.next_policy_target.array[slot_id, :rows].copy(),
            "next_value_target": self.next_value_target.array[slot_id, :rows].copy(),
            "recurrent_mask": self.recurrent_mask.array[slot_id, :rows].copy(),
            "policy_target": self.policy_target.array[slot_id, :rows].copy(),
            "value_target": self.value_target.array[slot_id, :rows].copy(),
            "reward_target": self.reward_target.array[slot_id, :rows].copy(),
            "phase": self.phase.array[slot_id, :rows].copy(),
            "move_index": self.move_index.array[slot_id, :rows].copy(),
            "variant_id": self.variant_id.array[slot_id, :rows].copy(),
            "weight_version": self.weight_version.array[slot_id, :rows].copy(),
        }

    def close(self) -> None:
        for array in (
            self.obs,
            self.legal_mask,
            self.action,
            self.next_obs,
            self.next_legal_mask,
            self.next_policy_target,
            self.next_value_target,
            self.recurrent_mask,
            self.policy_target,
            self.value_target,
            self.reward_target,
            self.phase,
            self.move_index,
            self.variant_id,
            self.weight_version,
        ):
            array.close()

    def unlink(self) -> None:
        for array in (
            self.obs,
            self.legal_mask,
            self.action,
            self.next_obs,
            self.next_legal_mask,
            self.next_policy_target,
            self.next_value_target,
            self.recurrent_mask,
            self.policy_target,
            self.value_target,
            self.reward_target,
            self.phase,
            self.move_index,
            self.variant_id,
            self.weight_version,
        ):
            array.unlink()
