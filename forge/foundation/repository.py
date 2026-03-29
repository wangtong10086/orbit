"""Filesystem-backed canonical repository implementations."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping

from forge.foundation.contracts import CanonicalRepository
from forge.foundation.schema import JsonValue


ENV_FILENAME_MAP = {
    "GAME": "game.jsonl",
    "NAVWORLD": "navworld.jsonl",
    "SWE-INFINITE": "swe_infinite.jsonl",
    "LIVEWEB": "liveweb.jsonl",
    "LGC-v2": "lgc_v2.jsonl",
    "PRINT": "print.jsonl",
}


def env_to_filename(env_name: str) -> str:
    """Convert an environment name into its canonical filename."""

    return ENV_FILENAME_MAP.get(env_name, f"{env_name.lower().replace('-', '_')}.jsonl")


def canonical_fingerprint(record: Mapping[str, JsonValue]) -> str:
    """Stable fingerprint for canonical-message deduplication."""

    payload = []
    for message in record.get("messages", []):
        payload.append(
            {
                "role": message.get("role", ""),
                "content": message.get("content", "") or "",
                "tool_calls": message.get("tool_calls"),
                "tool_call_id": message.get("tool_call_id"),
                "tools": message.get("tools"),
            }
        )
    return hashlib.md5(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


class LocalCanonicalRepository(CanonicalRepository):
    """Canonical repository backed by local JSONL files."""

    def __init__(self, root_dir: str = "data/canonical"):
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def exists(self, env_name: str, fingerprint: str) -> bool:
        return fingerprint in self.fingerprint_set(env_name)

    def append(self, env_name: str, records: list[Mapping[str, JsonValue]]) -> int:
        path = self.path_for(env_name)
        written = 0
        with path.open("a", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                written += 1
        return written

    def path_for(self, env_name: str) -> Path:
        return self.root_dir / env_to_filename(env_name)

    def load(self, env_name: str) -> list[dict[str, JsonValue]]:
        path = self.path_for(env_name)
        if not path.exists():
            return []
        entries: list[dict[str, JsonValue]] = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries

    def fingerprint_set(self, env_name: str) -> set[str]:
        return {canonical_fingerprint(entry) for entry in self.load(env_name)}
