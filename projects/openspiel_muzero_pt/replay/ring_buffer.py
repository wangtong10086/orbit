from __future__ import annotations

import numpy as np


class ArrayRingBuffer:
    def __init__(self, *, capacity: int):
        self.capacity = max(int(capacity), 1)
        self._storage: dict[str, np.ndarray] | None = None
        self._size = 0
        self._head = 0

    def __len__(self) -> int:
        return self._size

    def append_chunk(self, payload: dict[str, np.ndarray]) -> None:
        normalized = {key: np.asarray(value) for key, value in payload.items()}
        if not normalized:
            raise ValueError("Cannot append an empty payload")
        rows = int(next(iter(normalized.values())).shape[0])
        if rows <= 0:
            return
        for key, value in normalized.items():
            if int(value.shape[0]) != rows:
                raise ValueError(f"Payload field {key} has mismatched leading dimension")
        if self._storage is None:
            self._storage = {
                key: np.empty((self.capacity, *value.shape[1:]), dtype=value.dtype) for key, value in normalized.items()
            }
        elif set(normalized) != set(self._storage):
            raise ValueError("Payload keys do not match ring buffer schema")
        if rows >= self.capacity:
            trimmed = {key: value[-self.capacity :] for key, value in normalized.items()}
            for key, value in trimmed.items():
                self._storage[key][:] = value
            self._head = 0
            self._size = self.capacity
            return
        free_rows = self.capacity - self._size
        write_start = (self._head + self._size) % self.capacity
        first_span = min(rows, self.capacity - write_start)
        second_span = rows - first_span
        for key, value in normalized.items():
            self._storage[key][write_start : write_start + first_span] = value[:first_span]
            if second_span > 0:
                self._storage[key][:second_span] = value[first_span:]
        overflow = max(rows - free_rows, 0)
        if overflow > 0:
            self._head = (self._head + overflow) % self.capacity
        self._size = min(self._size + rows, self.capacity)

    def materialize(self) -> dict[str, np.ndarray]:
        if self._storage is None or self._size == 0:
            raise ValueError("Cannot materialize an empty ring buffer")
        if self._size < self.capacity:
            return {key: value[: self._size].copy() for key, value in self._storage.items()}
        if self._head == 0:
            return {key: value.copy() for key, value in self._storage.items()}
        return {
            key: np.concatenate([value[self._head :], value[: self._head]], axis=0).copy()
            for key, value in self._storage.items()
        }

    def sample_batch(self, batch_size: int, *, rng: np.random.Generator) -> dict[str, np.ndarray]:
        if self._storage is None or self._size == 0:
            raise ValueError("Cannot sample from an empty ring buffer")
        logical = self.materialize()
        indices = rng.integers(0, self._size, size=max(int(batch_size), 1))
        return {key: value[indices] for key, value in logical.items()}
