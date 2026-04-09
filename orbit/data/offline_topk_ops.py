"""Helpers for validating and publishing offline-topk GKD datasets."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


REQUIRED_OFFLINE_TOPK_FIELDS = (
    "messages",
    "response_token_ids",
    "teacher_topk_indices",
    "teacher_topk_logprobs",
)


def _resolve_token(token: str | None = None) -> str:
    return token or os.environ.get("HF_TOKEN", "")


def validate_offline_topk_jsonl(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Validate a response-only offline-topk JSONL file and return summary stats."""

    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(target)

    row_count = 0
    topk_width: int | None = None
    example: dict[str, Any] | None = None

    with target.open(encoding="utf-8") as handle:
        for row_index, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line:
                continue
            row = json.loads(line)
            row_count += 1
            if example is None:
                example = row

            missing = [field for field in REQUIRED_OFFLINE_TOPK_FIELDS if field not in row]
            if missing:
                raise ValueError(f"row {row_index} missing required fields: {', '.join(missing)}")

            messages = row["messages"]
            if not isinstance(messages, list) or not messages:
                raise ValueError(f"row {row_index} has invalid messages payload")
            last = messages[-1]
            if not isinstance(last, dict) or last.get("role") != "assistant":
                raise ValueError(f"row {row_index} must end with an assistant message")

            response_ids = row["response_token_ids"]
            indices = row["teacher_topk_indices"]
            logprobs = row["teacher_topk_logprobs"]
            if not isinstance(response_ids, list) or not response_ids:
                raise ValueError(f"row {row_index} has empty response_token_ids")
            if not isinstance(indices, list) or not isinstance(logprobs, list):
                raise ValueError(f"row {row_index} teacher_topk fields must be lists")
            if len(indices) != len(response_ids) or len(logprobs) != len(response_ids):
                raise ValueError(
                    f"row {row_index} response_token_ids and teacher_topk row counts must match"
                )

            local_width: int | None = None
            for pos, (idx_row, lp_row) in enumerate(zip(indices, logprobs), start=1):
                if not isinstance(idx_row, list) or not isinstance(lp_row, list):
                    raise ValueError(f"row {row_index} top-k position {pos} is not list-shaped")
                if len(idx_row) != len(lp_row):
                    raise ValueError(f"row {row_index} top-k position {pos} index/logprob width mismatch")
                if local_width is None:
                    local_width = len(idx_row)
                    if local_width <= 0:
                        raise ValueError(f"row {row_index} top-k width must be > 0")
                elif len(idx_row) != local_width:
                    raise ValueError(f"row {row_index} has inconsistent top-k widths")

            if local_width is None:
                raise ValueError(f"row {row_index} has no teacher top-k rows")
            if topk_width is None:
                topk_width = local_width

    if row_count == 0:
        raise ValueError("offline-topk dataset is empty")

    return {
        "path": str(target),
        "rows": row_count,
        "topk_width": topk_width,
        "required_fields": list(REQUIRED_OFFLINE_TOPK_FIELDS),
        "example_fields": sorted(example.keys()) if example else [],
    }


def upload_offline_topk_jsonl(
    *,
    path: str | os.PathLike[str],
    repo_id: str,
    path_in_repo: str = "",
    token: str | None = None,
    create_repo: bool = False,
    private: bool = True,
) -> dict[str, Any]:
    """Upload a validated offline-topk JSONL file to a Hugging Face dataset repo."""

    from huggingface_hub import HfApi

    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(target)

    resolved_token = _resolve_token(token)
    if not resolved_token:
        raise ValueError("HF_TOKEN is required to upload offline-topk datasets")

    remote_path = path_in_repo or f"offline_topk/{target.name}"
    api = HfApi(token=resolved_token)
    if create_repo:
        api.create_repo(repo_id=repo_id, repo_type="dataset", private=private, exist_ok=True)
    api.upload_file(
        path_or_fileobj=str(target),
        path_in_repo=remote_path,
        repo_id=repo_id,
        repo_type="dataset",
        commit_message=f"offline_topk: upload {remote_path}",
    )
    return {
        "status": "success",
        "repo_id": repo_id,
        "repo_type": "dataset",
        "path_in_repo": remote_path,
        "path": str(target),
    }


__all__ = [
    "REQUIRED_OFFLINE_TOPK_FIELDS",
    "upload_offline_topk_jsonl",
    "validate_offline_topk_jsonl",
]
