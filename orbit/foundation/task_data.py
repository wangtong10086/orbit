"""Generic task-source and conversation helpers."""

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
    target.write_text(json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n", encoding="utf-8")


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


def normalize_messages(messages: object, *, prompt: str = "") -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    raw_messages = messages if isinstance(messages, list) else []
    for raw in raw_messages:
        if not isinstance(raw, dict):
            continue
        role = str(raw.get("role", "")).strip()
        content = str(raw.get("content", ""))
        if role:
            normalized.append({"role": role, "content": content})
    if normalized:
        return normalized
    if prompt:
        return [{"role": "user", "content": prompt}]
    return []


def normalize_steps(steps: object) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    raw_steps = steps if isinstance(steps, list) else []
    for idx, raw in enumerate(raw_steps):
        if isinstance(raw, str):
            normalized.append({"index": idx, "role": "assistant", "content": raw})
            continue
        if not isinstance(raw, dict):
            continue
        normalized.append(
            {
                "index": int(raw.get("index", idx)),
                "role": str(raw.get("role", "assistant")),
                "content": str(raw.get("content", raw.get("text", ""))),
                "metadata": dict(raw.get("metadata", {}) or {}),
            }
        )
    return normalized


def assistant_text(steps: object) -> str:
    parts: list[str] = []
    for step in normalize_steps(steps):
        if str(step.get("role", "assistant")) == "assistant":
            content = str(step.get("content", "")).strip()
            if content:
                parts.append(content)
    return "\n".join(parts).strip()


def cumulative_step_texts(steps: object) -> list[str]:
    seen: list[str] = []
    cumulative: list[str] = []
    for step in normalize_steps(steps):
        content = str(step.get("content", "")).strip()
        if content:
            seen.append(content)
        cumulative.append("\n".join(seen).strip())
    return cumulative


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


def ensure_student_steps(record: dict, *, response: str) -> list[dict[str, object]]:
    if record.get("student_steps"):
        return normalize_steps(record.get("student_steps"))
    return normalize_steps([{"role": "assistant", "content": response}])


def padded_floats(values: object, *, length: int, default: float = 0.0) -> list[float]:
    raw = list(values) if isinstance(values, list) else []
    padded = [float(item or 0.0) for item in raw[:length]]
    if len(padded) < length:
        padded.extend([default] * (length - len(padded)))
    return padded


def discounted_returns(rewards: list[float], *, gamma: float) -> list[float]:
    running = 0.0
    returns = [0.0] * len(rewards)
    for idx in range(len(rewards) - 1, -1, -1):
        running = rewards[idx] + gamma * running
        returns[idx] = running
    return returns


def detect_switch_step(*, explicit_switch_step: object, local_scores: list[float], potentials: list[float], success_threshold: float) -> int:
    if explicit_switch_step is not None and str(explicit_switch_step).strip():
        try:
            return max(0, int(explicit_switch_step))
        except (TypeError, ValueError):
            pass
    for idx, score in enumerate(local_scores):
        if score < success_threshold:
            return idx
    for idx in range(1, len(potentials)):
        if potentials[idx] < potentials[idx - 1]:
            return idx
    return max(len(local_scores) - 1, 0)


__all__ = [
    "assistant_text",
    "candidate_response",
    "cumulative_step_texts",
    "detect_switch_step",
    "discounted_returns",
    "ensure_student_steps",
    "first_error_index",
    "load_jsonl",
    "normalize_messages",
    "normalize_steps",
    "normalize_text",
    "padded_floats",
    "progress_score",
    "write_json",
    "write_jsonl",
]
