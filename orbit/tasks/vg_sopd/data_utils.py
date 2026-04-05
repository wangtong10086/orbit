"""Shared helpers for VG-SOPD stage runners."""

from __future__ import annotations

import json
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable


def load_jsonl(path: str | Path) -> list[dict]:
    records: list[dict] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def write_jsonl(path: str | Path, records: Iterable[dict]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")


def write_json(path: str | Path, payload: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True) + "\n", encoding="utf-8")


def normalize_text(value: str) -> str:
    return " ".join(str(value).strip().split())


def progress_score(expected: str, observed: str) -> float:
    expected_norm = normalize_text(expected)
    observed_norm = normalize_text(observed)
    if not expected_norm and not observed_norm:
        return 1.0
    if not expected_norm:
        return 0.0
    return SequenceMatcher(a=expected_norm, b=observed_norm).ratio()


def first_error_index(expected: str, observed: str) -> int:
    expected_norm = normalize_text(expected)
    observed_norm = normalize_text(observed)
    for idx, (left, right) in enumerate(zip(expected_norm, observed_norm)):
        if left != right:
            return idx
    return min(len(expected_norm), len(observed_norm))


def candidate_response(record: dict, sample_index: int) -> str:
    candidates = record.get("student_candidates") or []
    if candidates:
        return str(candidates[sample_index % len(candidates)])
    if record.get("student_response"):
        return str(record["student_response"])
    expected = str(record.get("expected_answer", "")).strip()
    if expected:
        if sample_index % 2 == 0:
            return expected
        return f"{expected} (draft)"
    prompt = str(record.get("prompt", "")).strip()
    if not prompt:
        return "no-op"
    return f"draft answer for: {prompt[:80]}"


__all__ = [
    "candidate_response",
    "first_error_index",
    "load_jsonl",
    "normalize_text",
    "progress_score",
    "write_json",
    "write_jsonl",
]
