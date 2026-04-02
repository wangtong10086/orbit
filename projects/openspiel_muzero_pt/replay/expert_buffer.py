from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

import numpy as np


@dataclass(slots=True)
class ReplaySample:
    obs: np.ndarray
    legal_mask: np.ndarray
    action: int
    next_obs: np.ndarray
    next_legal_mask: np.ndarray
    next_policy_target: np.ndarray
    next_value_target: float
    recurrent_mask: float
    policy_target: np.ndarray
    value_target: float
    reward_target: float
    phase: float
    move_index: int
    variant_id: int
    weight_version: int


def pack_samples(samples: list[ReplaySample]) -> dict[str, np.ndarray]:
    if not samples:
        raise ValueError("Cannot pack an empty sample list")
    return {
        "obs": np.stack([sample.obs for sample in samples]).astype(np.float32),
        "legal_mask": np.stack([sample.legal_mask for sample in samples]).astype(np.float32),
        "action": np.asarray([sample.action for sample in samples], dtype=np.int64),
        "next_obs": np.stack([sample.next_obs for sample in samples]).astype(np.float32),
        "next_legal_mask": np.stack([sample.next_legal_mask for sample in samples]).astype(np.float32),
        "next_policy_target": np.stack([sample.next_policy_target for sample in samples]).astype(np.float32),
        "next_value_target": np.asarray([sample.next_value_target for sample in samples], dtype=np.float32),
        "recurrent_mask": np.asarray([sample.recurrent_mask for sample in samples], dtype=np.float32),
        "policy_target": np.stack([sample.policy_target for sample in samples]).astype(np.float32),
        "value_target": np.asarray([sample.value_target for sample in samples], dtype=np.float32),
        "reward_target": np.asarray([sample.reward_target for sample in samples], dtype=np.float32),
        "phase": np.asarray([sample.phase for sample in samples], dtype=np.float32),
        "move_index": np.asarray([sample.move_index for sample in samples], dtype=np.int64),
        "variant_id": np.asarray([sample.variant_id for sample in samples], dtype=np.int64),
        "weight_version": np.asarray([sample.weight_version for sample in samples], dtype=np.int64),
    }


def unpack_samples(payload: dict[str, np.ndarray]) -> list[ReplaySample]:
    total = int(payload["action"].shape[0])
    samples = []
    for index in range(total):
        samples.append(
            ReplaySample(
                obs=payload["obs"][index],
                legal_mask=payload["legal_mask"][index],
                action=int(payload["action"][index]),
                next_obs=payload["next_obs"][index],
                next_legal_mask=payload["next_legal_mask"][index],
                next_policy_target=payload["next_policy_target"][index],
                next_value_target=float(payload["next_value_target"][index]),
                recurrent_mask=float(payload["recurrent_mask"][index]),
                policy_target=payload["policy_target"][index],
                value_target=float(payload["value_target"][index]),
                reward_target=float(payload["reward_target"][index]),
                phase=float(payload["phase"][index]),
                move_index=int(payload["move_index"][index]),
                variant_id=int(payload["variant_id"][index]),
                weight_version=int(payload["weight_version"][index]),
            )
        )
    return samples


class ExpertShardWriter:
    def __init__(self, output_dir: str | Path, *, shard_size: int = 4096):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.shard_size = max(int(shard_size), 1)
        self._buffer: list[ReplaySample] = []
        self._shard_index = 0

    def add(self, sample: ReplaySample) -> None:
        self._buffer.append(sample)
        if len(self._buffer) >= self.shard_size:
            self.flush()

    def flush(self) -> None:
        if not self._buffer:
            return
        shard_path = self.output_dir / f"expert_{self._shard_index:06d}.npz"
        np.savez_compressed(shard_path, **pack_samples(self._buffer))
        meta_path = shard_path.with_suffix(".json")
        meta_path.write_text(json.dumps({"rows": len(self._buffer)}, indent=2), encoding="utf-8")
        self._buffer.clear()
        self._shard_index += 1


class ExpertBuffer:
    def __init__(self, shard_paths: list[str | Path]):
        self.shard_paths = [Path(path) for path in shard_paths]
        self._payloads: list[dict[str, np.ndarray]] | None = None

    @classmethod
    def from_dir(cls, directory: str | Path) -> "ExpertBuffer":
        shard_paths = sorted(Path(directory).glob("*.npz"))
        if not shard_paths:
            raise FileNotFoundError(f"No expert shards found under {directory}")
        return cls(list(shard_paths))

    def _ensure_loaded(self) -> list[dict[str, np.ndarray]]:
        if self._payloads is None:
            self._payloads = [dict(np.load(path)) for path in self.shard_paths]
        return self._payloads

    def __len__(self) -> int:
        return int(sum(payload["action"].shape[0] for payload in self._ensure_loaded()))

    def load_all(self) -> dict[str, np.ndarray]:
        payloads = self._ensure_loaded()
        keys = payloads[0].keys()
        merged: dict[str, np.ndarray] = {}
        for key in keys:
            merged[key] = np.concatenate([payload[key] for payload in payloads], axis=0)
        return merged

    def sample_batch(self, batch_size: int, *, rng: np.random.Generator) -> dict[str, np.ndarray]:
        merged = self.load_all()
        total = int(merged["action"].shape[0])
        indices = rng.integers(0, total, size=int(batch_size))
        return {key: value[indices] for key, value in merged.items()}
