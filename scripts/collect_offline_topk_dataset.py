#!/usr/bin/env python3
"""Prepare, collect, and upload offline-topk teacher data at production scale."""

from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from orbit.config import load_dotenv
from orbit.data.offline_topk_ops import prepare_offline_topk_collection_dataset, upload_offline_topk_jsonl
from orbit.integrations.ms_swift_offline_topk import (
    build_offline_topk_rows_from_teacher_batch,
    iter_prepared_rows,
    resolve_teacher_server_model_id,
)


def _bucket_rows(max_length: int, boundaries: dict[str, int]) -> int:
    if max_length <= boundaries["b8"]:
        return 64
    if max_length <= boundaries["b16"]:
        return 32
    return 8


def _load_manifest(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _save_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _flush_part(
    *,
    bucket_dir: Path,
    bucket_name: str,
    prefix: str,
    part_index: int,
    rows: list[dict[str, Any]],
    hf_repo: str,
    hf_prefix: str,
    create_repo: bool,
    public: bool,
    uploads_enabled: bool,
) -> dict[str, Any]:
    part_name = f"part-{part_index:05d}.jsonl"
    part_path = bucket_dir / part_name
    with part_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    result = {
        "bucket": bucket_name,
        "part_name": part_name,
        "path": str(part_path),
        "rows": len(rows),
    }
    if uploads_enabled:
        remote_path = f"{hf_prefix.rstrip('/')}/{bucket_name}/{part_name}"
        upload = upload_offline_topk_jsonl(
            path=part_path,
            repo_id=hf_repo,
            path_in_repo=remote_path,
            create_repo=create_repo,
            private=not public,
        )
        result["upload"] = upload
    return result


def _collect_bucket(
    *,
    bucket_name: str,
    prepared_path: Path,
    output_dir: Path,
    teacher_model_server: str,
    teacher_model_name: str,
    topk: int,
    request_batch_size: int,
    max_inflight_requests: int,
    flush_rows: int,
    flush_seconds: int,
    hf_repo: str,
    hf_prefix: str,
    create_repo: bool,
    public: bool,
    state: dict[str, Any],
) -> dict[str, Any]:
    bucket_dir = output_dir / bucket_name
    bucket_dir.mkdir(parents=True, exist_ok=True)

    uploaded_parts = list(state.get("uploaded_parts", []))
    next_row_index = int(state.get("next_row_index", 0))
    part_index = int(state.get("next_part_index", 0))
    completed_rows = int(state.get("completed_rows", 0))
    create_repo_flag = create_repo and not uploaded_parts

    rows_iter = iter_prepared_rows(prepared_path)
    for _ in range(next_row_index):
        try:
            next(rows_iter)
        except StopIteration:
            return {
                **state,
                "status": "completed",
                "completed_rows": completed_rows,
                "next_row_index": next_row_index,
                "next_part_index": part_index,
                "uploaded_parts": uploaded_parts,
            }

    inflight_batches = max(1, max_inflight_requests // max(1, request_batch_size))
    executor = ThreadPoolExecutor(max_workers=inflight_batches)
    pending: list[tuple[int, list[dict[str, Any]], Future[list[dict[str, Any]]]]] = []
    buffer: list[dict[str, Any]] = []
    last_flush = time.time()
    source_index = next_row_index

    def submit_batch(batch_rows: list[dict[str, Any]], start_index: int):
        future = executor.submit(
            build_offline_topk_rows_from_teacher_batch,
            batch_rows,
            base_url=teacher_model_server,
            topk=topk,
            model_name=teacher_model_name,
            max_workers=request_batch_size,
        )
        pending.append((start_index, batch_rows, future))

    def maybe_flush(force: bool = False):
        nonlocal buffer, part_index, last_flush, create_repo_flag
        if not buffer:
            return None
        if not force and len(buffer) < flush_rows and (time.time() - last_flush) < flush_seconds:
            return None
        result = None
        while buffer and (force or len(buffer) >= flush_rows):
            chunk_rows = buffer[:flush_rows] if not force else buffer[:flush_rows]
            if not chunk_rows:
                break
            result = _flush_part(
                bucket_dir=bucket_dir,
                bucket_name=bucket_name,
                prefix=hf_prefix,
                part_index=part_index,
                rows=chunk_rows,
                hf_repo=hf_repo,
                hf_prefix=hf_prefix,
                create_repo=create_repo_flag,
                public=public,
                uploads_enabled=bool(hf_repo),
            )
            create_repo_flag = False
            uploaded_parts.append(result["part_name"])
            buffer = buffer[len(chunk_rows):]
            part_index += 1
            last_flush = time.time()
            if not force and len(buffer) < flush_rows:
                break
        return result

    while True:
        while len(pending) < inflight_batches:
            batch_rows: list[dict[str, Any]] = []
            batch_start = source_index
            try:
                for _ in range(request_batch_size):
                    batch_rows.append(next(rows_iter))
                    source_index += 1
            except StopIteration:
                pass
            if not batch_rows:
                break
            submit_batch(batch_rows, batch_start)
        if not pending:
            break

        batch_start, batch_rows, future = pending.pop(0)
        rows = future.result()
        buffer.extend(rows)
        completed_rows += len(rows)
        next_row_index = batch_start + len(batch_rows)
        maybe_flush()

    executor.shutdown(wait=True)
    maybe_flush(force=True)
    return {
        "status": "completed",
        "prepared_path": str(prepared_path),
        "completed_rows": completed_rows,
        "next_row_index": next_row_index,
        "next_part_index": part_index,
        "uploaded_parts": uploaded_parts,
        "request_batch_size": request_batch_size,
        "max_inflight_requests": max_inflight_requests,
    }


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Collect offline-topk teacher data without using swift sample")
    parser.add_argument("--dataset", required=True, help="Messages-only source JSONL")
    parser.add_argument("--output-dir", required=True, help="Working directory for prepared files and outputs")
    parser.add_argument("--model", required=True, help="Student tokenizer/model family")
    parser.add_argument("--teacher-model-server", required=True, help="OpenAI-compatible teacher base URL")
    parser.add_argument("--gkd-logits-topk", type=int, required=True, help="Teacher top-k width")
    parser.add_argument("--max-length", type=int, default=32768)
    parser.add_argument("--bucket-boundaries", default="8192,16384,32768")
    parser.add_argument("--hf-repo", default="", help="HF dataset repo for incremental part uploads")
    parser.add_argument("--hf-prefix", default="offline_topk/canonical")
    parser.add_argument("--create-repo", action="store_true")
    parser.add_argument("--public", action="store_true")
    parser.add_argument("--request-batch-size", type=int, default=8)
    parser.add_argument("--b8-inflight", type=int, default=64)
    parser.add_argument("--b16-inflight", type=int, default=32)
    parser.add_argument("--b32-inflight", type=int, default=8)
    parser.add_argument("--flush-rows", type=int, default=512)
    parser.add_argument("--flush-seconds", type=int, default=900)
    parser.add_argument("--force-reprepare", action="store_true")
    args = parser.parse_args()

    boundaries = tuple(int(item.strip()) for item in args.bucket_boundaries.split(","))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    prepared_manifest_path = output_dir / "prepared_manifest.json"
    collection_manifest_path = output_dir / "collection_manifest.json"

    if args.force_reprepare or not prepared_manifest_path.exists():
        prepared_manifest = prepare_offline_topk_collection_dataset(
            path=args.dataset,
            output_dir=output_dir,
            model=args.model,
            max_length=args.max_length,
            bucket_boundaries=boundaries,
        )
    else:
        prepared_manifest = json.loads(prepared_manifest_path.read_text(encoding="utf-8"))

    collection_manifest = _load_manifest(collection_manifest_path)
    if not collection_manifest:
        collection_manifest = {
            "source_dataset": args.dataset,
            "prepared_manifest_path": str(prepared_manifest_path),
            "teacher_model_server": args.teacher_model_server,
            "gkd_logits_topk": args.gkd_logits_topk,
            "max_length": args.max_length,
            "buckets": {},
        }

    teacher_model_name = resolve_teacher_server_model_id(args.teacher_model_server)
    inflight_by_bucket = {
        "b8": args.b8_inflight,
        "b16": args.b16_inflight,
        "b32": args.b32_inflight,
    }
    for bucket_name in ("b8", "b16", "b32"):
        bucket_info = prepared_manifest["buckets"][bucket_name]
        bucket_state = collection_manifest["buckets"].get(bucket_name, {})
        if int(bucket_info["rows"]) <= 0:
            collection_manifest["buckets"][bucket_name] = {
                **bucket_state,
                "status": "skipped",
                "prepared_path": bucket_info["path"],
                "completed_rows": 0,
                "total_rows": 0,
            }
            _save_manifest(collection_manifest_path, collection_manifest)
            continue

        bucket_state = _collect_bucket(
            bucket_name=bucket_name,
            prepared_path=Path(bucket_info["path"]),
            output_dir=output_dir / "collected",
            teacher_model_server=args.teacher_model_server,
            teacher_model_name=teacher_model_name,
            topk=args.gkd_logits_topk,
            request_batch_size=args.request_batch_size,
            max_inflight_requests=inflight_by_bucket[bucket_name],
            flush_rows=args.flush_rows,
            flush_seconds=args.flush_seconds,
            hf_repo=args.hf_repo.strip(),
            hf_prefix=args.hf_prefix,
            create_repo=args.create_repo,
            public=args.public,
            state=bucket_state,
        )
        bucket_state["total_rows"] = int(bucket_info["rows"])
        collection_manifest["buckets"][bucket_name] = bucket_state
        _save_manifest(collection_manifest_path, collection_manifest)

    print(json.dumps(collection_manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
