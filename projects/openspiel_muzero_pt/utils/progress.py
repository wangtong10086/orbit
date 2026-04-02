from __future__ import annotations

from dataclasses import dataclass
import json
import time
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def eta_seconds(*, started_at: float, completed: int, total: int) -> float | None:
    if completed <= 0 or total <= completed:
        return 0.0 if total <= completed else None
    elapsed = max(time.time() - float(started_at), 1e-6)
    rate = completed / elapsed
    if rate <= 0:
        return None
    remaining = max(total - completed, 0)
    return remaining / rate


class JsonProgressWriter:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, payload: dict[str, Any]) -> None:
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(self.path)


class JsonlEventWriter:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, payload: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def append_event(writer: JsonlEventWriter | None, *, kind: str, **payload: Any) -> None:
    event = {"ts": utc_now(), "kind": kind, **payload}
    line = json.dumps(event, ensure_ascii=False)
    print(line, flush=True)
    if writer is not None:
        writer.append(event)
