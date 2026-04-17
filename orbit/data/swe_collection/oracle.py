"""Hidden oracle extraction and scoring for staged SWE collection."""

from __future__ import annotations

import re
from pathlib import Path

from orbit.foundation.data_contracts import SweIssueOracleV1


_SYMBOL_RE = re.compile(
    r"(?:def|class|fn|func|struct|interface|trait|enum|module|mod)\s+([A-Za-z_][A-Za-z0-9_]*)|"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*\("
)


def _extract_touched_files(patch: str) -> tuple[str, ...]:
    files: list[str] = []
    seen: set[str] = set()
    for line in patch.splitlines():
        if not line.startswith("+++ b/"):
            continue
        path = line[6:].strip()
        if path and path not in seen:
            files.append(path)
            seen.add(path)
    return tuple(files)


def _extract_symbols(patch: str) -> tuple[str, ...]:
    found: list[str] = []
    seen: set[str] = set()
    for line in patch.splitlines():
        text = line[1:] if line.startswith(("+", "-", " ")) else line
        for left, right in _SYMBOL_RE.findall(text):
            symbol = (left or right).strip()
            if len(symbol) < 3 or symbol in seen:
                continue
            found.append(symbol)
            seen.add(symbol)
    return tuple(found[:24])


def infer_edit_type(patch: str) -> str:
    lowered = patch.lower()
    if any(token in lowered for token in (" none", "null", "nil", "nullptr", "optional")):
        return "null_check"
    if any(token in lowered for token in ("len(", "length", "size", "index", "bound", "range", "offset")):
        return "boundary"
    if any(token in lowered for token in ("guard", "early return", "if !", "if not", "return err")):
        return "guard"
    if any(token in lowered for token in ("deprecated", "migrate", "rename", "signature", "api")):
        return "api_migration"
    touched_files = _extract_touched_files(patch)
    if len(touched_files) > 2:
        return "refactor"
    return "unknown"


def _related_tests(task: dict) -> tuple[str, ...]:
    tests: list[str] = []
    seen: set[str] = set()
    for key in ("fail_to_pass", "pass_to_pass"):
        for item in task.get(key, []) or []:
            text = str(item)
            path = text.split("::", 1)[0].strip()
            if not path:
                continue
            if path not in seen:
                tests.append(path)
                seen.add(path)
    command = str(task.get("test_command", "")).strip()
    for token in command.replace('"', " ").replace("'", " ").split():
        if "/" in token and any(part.startswith("test") or part.startswith("spec") for part in Path(token).parts):
            if token not in seen:
                tests.append(token)
                seen.add(token)
    return tuple(tests)


def build_hidden_oracle(task: dict) -> SweIssueOracleV1:
    patch = str(task.get("patch", "") or "")
    touched_files = _extract_touched_files(patch)
    line_changes = sum(1 for line in patch.splitlines() if line.startswith(("+", "-")) and not line.startswith(("+++", "---")))
    patch_size_lower = max(1, line_changes // 2) if line_changes else 1
    patch_size_upper = max(patch_size_lower, line_changes + max(4, len(touched_files) * 2))
    return SweIssueOracleV1(
        base_instance_id=str(task.get("instance_id", "")),
        touched_files=touched_files,
        touched_symbols=_extract_symbols(patch),
        edit_type=infer_edit_type(patch),
        related_tests=_related_tests(task),
        patch_size_lower=patch_size_lower,
        patch_size_upper=patch_size_upper,
        metadata={
            "repo": task.get("repo", ""),
            "task_id": task.get("task_id"),
        },
    )


def score_path_overlap(predicted: tuple[str, ...], expected: tuple[str, ...]) -> float:
    if not expected:
        return 0.5 if predicted else 0.0
    if not predicted:
        return 0.0
    predicted_set = set(predicted)
    expected_set = set(expected)
    exact = len(predicted_set & expected_set) / len(expected_set)
    if exact > 0:
        return min(1.0, exact)
    predicted_names = {Path(item).name for item in predicted_set}
    expected_names = {Path(item).name for item in expected_set}
    basename = len(predicted_names & expected_names) / len(expected_names)
    return basename * 0.6


def score_symbol_overlap(predicted: tuple[str, ...], expected: tuple[str, ...]) -> float:
    if not expected:
        return 0.5 if predicted else 0.0
    if not predicted:
        return 0.0
    predicted_set = {item.lower() for item in predicted}
    expected_set = {item.lower() for item in expected}
    return len(predicted_set & expected_set) / len(expected_set)


def score_edit_type(predicted: str, expected: str) -> float:
    if not expected or expected == "unknown":
        return 0.5
    if not predicted or predicted == "unknown":
        return 0.25
    return 1.0 if predicted == expected else 0.0


def score_patch_size(line_count: int, oracle: SweIssueOracleV1) -> float:
    if line_count <= 0:
        return 0.0
    if oracle.patch_size_lower <= line_count <= oracle.patch_size_upper:
        return 1.0
    delta = min(abs(line_count - oracle.patch_size_lower), abs(line_count - oracle.patch_size_upper))
    return max(0.0, 1.0 - (delta / max(oracle.patch_size_upper, 1)))


def aggregate_oracle_scores(
    *,
    files: tuple[str, ...],
    symbols: tuple[str, ...],
    edit_type: str,
    patch_line_count: int = 0,
    oracle: SweIssueOracleV1,
) -> dict[str, float]:
    scores = {
        "file_overlap": score_path_overlap(files, oracle.touched_files),
        "symbol_overlap": score_symbol_overlap(symbols, oracle.touched_symbols),
        "edit_type": score_edit_type(edit_type, oracle.edit_type),
    }
    if patch_line_count:
        scores["patch_size"] = score_patch_size(patch_line_count, oracle)
    scores["total"] = (
        scores["file_overlap"] * 0.55
        + scores["symbol_overlap"] * 0.2
        + scores["edit_type"] * 0.15
        + scores.get("patch_size", 0.5) * 0.1
    )
    return scores


def score_rubric_alignment(
    *,
    files: tuple[str, ...],
    symbols: tuple[str, ...],
    hypothesis: str,
    rubric: dict | None,
) -> float:
    if not rubric:
        return 0.5
    preferred = tuple(str(item) for item in rubric.get("likely_modules", ()) or ())
    forbidden = tuple(str(item) for item in rubric.get("forbidden_patterns", ()) or ())
    constraints = tuple(str(item) for item in rubric.get("required_constraints", ()) or ())
    text_blob = " ".join([*files, *symbols, hypothesis]).lower()
    score = 0.5
    if preferred:
        matched = sum(1 for item in preferred if item.lower() in text_blob)
        score += min(0.3, matched * 0.15)
    if constraints:
        matched = sum(1 for item in constraints if item.lower() in text_blob)
        score += min(0.2, matched * 0.1)
    if forbidden and any(item.lower() in text_blob for item in forbidden):
        score -= 0.4
    return max(0.0, min(1.0, score))


__all__ = [
    "aggregate_oracle_scores",
    "build_hidden_oracle",
    "infer_edit_type",
    "score_rubric_alignment",
]
