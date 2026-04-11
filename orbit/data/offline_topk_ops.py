"""Helpers for validating, filtering, preparing, and publishing offline-topk GKD datasets."""

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


def filter_messages_jsonl_by_max_length(
    *,
    path: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    model: str,
    max_length: int,
) -> dict[str, Any]:
    """Filter a messages-only JSONL dataset down to rows whose tokenized length fits."""

    from transformers import AutoTokenizer

    source = Path(path)
    target = Path(output_path)
    if not source.exists():
        raise FileNotFoundError(source)
    if max_length <= 0:
        raise ValueError("max_length must be > 0")

    tokenizer = AutoTokenizer.from_pretrained(model, trust_remote_code=True)
    kept = 0
    dropped = 0
    max_seen = 0
    target.parent.mkdir(parents=True, exist_ok=True)

    with source.open(encoding="utf-8") as src, target.open("w", encoding="utf-8") as dst:
        for row_index, raw in enumerate(src, start=1):
            line = raw.strip()
            if not line:
                continue
            row = json.loads(line)
            messages = row.get("messages")
            if not isinstance(messages, list) or not messages:
                raise ValueError(f"row {row_index} has invalid messages payload")
            token_length = len(
                tokenizer.apply_chat_template(
                    messages,
                    tokenize=True,
                    add_generation_prompt=False,
                )
            )
            max_seen = max(max_seen, token_length)
            if token_length > max_length:
                dropped += 1
                continue
            kept += 1
            dst.write(json.dumps(row, ensure_ascii=False) + "\n")

    return {
        "source_path": str(source),
        "output_path": str(target),
        "model": model,
        "max_length": max_length,
        "kept_rows": kept,
        "dropped_rows": dropped,
        "max_seen_length": max_seen,
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


def _bucket_name(token_length: int, boundaries: tuple[int, int, int]) -> str | None:
    b8, b16, b32 = boundaries
    if token_length <= b8:
        return "b8"
    if token_length <= b16:
        return "b16"
    if token_length <= b32:
        return "b32"
    return None


def prepare_offline_topk_collection_dataset(
    *,
    path: str | os.PathLike[str],
    output_dir: str | os.PathLike[str],
    model: str,
    max_length: int = 32768,
    bucket_boundaries: tuple[int, int, int] = (8192, 16384, 32768),
    use_hf: bool = True,
    template_type: str | None = None,
    agent_template: str | None = None,
) -> dict[str, Any]:
    from swift.template import MaxLengthError

    from orbit.integrations.ms_swift_offline_topk import (
        build_offline_topk_encoder,
        encode_messages_for_offline_topk,
    )

    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(source)
    if max_length <= 0:
        raise ValueError("max_length must be > 0")
    if len(bucket_boundaries) != 3 or tuple(sorted(bucket_boundaries)) != tuple(bucket_boundaries):
        raise ValueError("bucket_boundaries must be a sorted 3-tuple like (8192, 16384, 32768)")

    target_dir = Path(output_dir)
    prepared_dir = target_dir / "prepared"
    prepared_dir.mkdir(parents=True, exist_ok=True)
    bucket_paths = {
        "b8": prepared_dir / "b8.prepared.jsonl",
        "b16": prepared_dir / "b16.prepared.jsonl",
        "b32": prepared_dir / "b32.prepared.jsonl",
    }
    counts = {name: 0 for name in bucket_paths}
    handles = {name: path.open("w", encoding="utf-8") for name, path in bucket_paths.items()}
    template = build_offline_topk_encoder(
        model,
        use_hf=use_hf,
        template_type=template_type,
        agent_template=agent_template,
        max_length=max_length,
    )

    total_rows = 0
    kept_rows = 0
    dropped_rows = 0
    dropped_invalid = 0
    dropped_oversize = 0
    max_seen_length = 0
    try:
        with source.open(encoding="utf-8") as src:
            for row_index, raw in enumerate(src, start=1):
                line = raw.strip()
                if not line:
                    continue
                total_rows += 1
                row = json.loads(line)
                messages = row.get("messages")
                if not isinstance(messages, list) or not messages:
                    dropped_invalid += 1
                    dropped_rows += 1
                    continue
                if messages[-1].get("role") != "assistant":
                    dropped_invalid += 1
                    dropped_rows += 1
                    continue
                try:
                    encoded = encode_messages_for_offline_topk(template, messages)
                except MaxLengthError:
                    dropped_oversize += 1
                    dropped_rows += 1
                    continue
                token_length = int(encoded["token_length"])
                max_seen_length = max(max_seen_length, token_length)
                bucket = _bucket_name(token_length, bucket_boundaries)
                if bucket is None:
                    dropped_oversize += 1
                    dropped_rows += 1
                    continue
                payload = {
                    "source_line": row_index,
                    "bucket": bucket,
                    "messages": messages,
                    "input_ids": encoded["input_ids"],
                    "response_positions": encoded["response_positions"],
                    "response_token_ids": encoded["response_token_ids"],
                    "token_length": token_length,
                }
                handles[bucket].write(json.dumps(payload, ensure_ascii=False) + "\n")
                counts[bucket] += 1
                kept_rows += 1
    finally:
        for handle in handles.values():
            handle.close()

    manifest = {
        "source_path": str(source),
        "prepared_dir": str(prepared_dir),
        "model": model,
        "max_length": max_length,
        "bucket_boundaries": {
            "b8": bucket_boundaries[0],
            "b16": bucket_boundaries[1],
            "b32": bucket_boundaries[2],
        },
        "total_rows": total_rows,
        "kept_rows": kept_rows,
        "dropped_rows": dropped_rows,
        "dropped_invalid": dropped_invalid,
        "dropped_oversize": dropped_oversize,
        "max_seen_length": max_seen_length,
        "buckets": {
            name: {
                "path": str(bucket_paths[name]),
                "rows": counts[name],
            }
            for name in ("b8", "b16", "b32")
        },
    }
    manifest_path = target_dir / "prepared_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest


__all__ = [
    "REQUIRED_OFFLINE_TOPK_FIELDS",
    "filter_messages_jsonl_by_max_length",
    "prepare_offline_topk_collection_dataset",
    "upload_offline_topk_jsonl",
    "validate_offline_topk_jsonl",
]
