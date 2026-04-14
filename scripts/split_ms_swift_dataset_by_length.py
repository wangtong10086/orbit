#!/usr/bin/env python3
"""Split a normalized ms-swift JSONL dataset into token-length buckets.

Operational invariants for the production bucket splitter:

- preserve bucket semantics; only optimize the way token lengths are computed
- prefer batch chat-template rendering plus batch tokenization over per-row
  ``apply_chat_template(..., tokenize=True)``
- stream bucket writes back to disk as completed batches arrive so operators can
  observe forward progress from file sizes and ``progress.json``
- keep ``manifest.json`` as the end-of-run artifact; use ``progress.json`` for
  in-flight visibility
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import multiprocessing as mp
from pathlib import Path
import queue
import re
import time

from transformers import AutoTokenizer

_TOKENIZER = None


def _slug(raw: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", raw).strip("-_.")
    return slug or "bucket"


def _legacy_plan(short_max: int, medium_max: int) -> dict:
    return {
        "stages": [
            {
                "name": f"le_{short_max}",
                "bucket_min_length": 0,
                "bucket_max_length": short_max,
                "output_filename": f"le_{short_max}.jsonl",
            },
            {
                "name": f"{short_max + 1}_{medium_max}",
                "bucket_min_length": short_max + 1,
                "bucket_max_length": medium_max,
                "output_filename": f"{short_max + 1}_{medium_max}.jsonl",
            },
            {
                "name": f"gt_{medium_max}",
                "bucket_min_length": medium_max + 1,
                "bucket_max_length": None,
                "output_filename": f"gt_{medium_max}.jsonl",
            },
        ]
    }


def _bucket_name(length: int, stages: list[dict]) -> str:
    for stage in stages:
        lower = int(stage.get("bucket_min_length", 0) or 0)
        upper = stage.get("bucket_max_length")
        if length < lower:
            continue
        if upper is None or length <= int(upper):
            return str(stage["name"])
    raise ValueError(f"token length {length} did not match any bucket stage")


def _get_tokenizer(model: str):
    global _TOKENIZER
    if _TOKENIZER is None:
        _TOKENIZER = AutoTokenizer.from_pretrained(model, trust_remote_code=True, use_fast=True)
    return _TOKENIZER


def _render_batch_messages(tok, batch_messages: list[list[dict]]) -> list[str]:
    # Qwen fast tokenizers can accept batched conversations here. If a model's
    # chat template cannot, fall back to per-row rendering while keeping the
    # tokenizer call batched.
    try:
        rendered = tok.apply_chat_template(
            batch_messages,
            tokenize=False,
            add_generation_prompt=False,
        )
        if isinstance(rendered, list) and len(rendered) == len(batch_messages):
            return [str(item) for item in rendered]
    except Exception:
        pass
    return [
        str(
            tok.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=False,
            )
        )
        for messages in batch_messages
    ]


def _batch_token_lengths(tok, rendered_batch: list[str]) -> list[int]:
    # Length calculation must stay semantically equivalent to the old path, but
    # should happen through one batched fast-tokenizer call.
    encoded = tok(
        rendered_batch,
        add_special_tokens=False,
        padding=False,
        truncation=False,
        return_attention_mask=False,
    )
    return [len(ids) for ids in encoded["input_ids"]]


def _worker(task_queue: mp.Queue, result_queue: mp.Queue, *, model: str, stages: list[dict], drop_unmatched: bool) -> None:
    tok = _get_tokenizer(model)
    while True:
        item = task_queue.get()
        if item is None:
            result_queue.put({"kind": "worker_done"})
            return
        batch_id, batch = item
        rows = [json.loads(line) for line in batch]
        messages_batch = [row["messages"] for row in rows]
        rendered_batch = _render_batch_messages(tok, messages_batch)
        lengths = _batch_token_lengths(tok, rendered_batch)
        bucket_payloads: dict[str, str] = {str(stage["name"]): "" for stage in stages}
        bucket_counts: Counter = Counter()
        bucket_tops: dict[str, list[int]] = {str(stage["name"]): [] for stage in stages}
        dropped_rows = 0

        for line, length in zip(batch, lengths):
            try:
                bucket = _bucket_name(length, stages)
            except ValueError:
                if not drop_unmatched:
                    raise
                dropped_rows += 1
                continue
            bucket_payloads[bucket] += line + "\n"
            bucket_counts[bucket] += 1
            arr = bucket_tops[bucket]
            arr.append(length)
            arr.sort(reverse=True)
            del arr[20:]

        # Return pre-grouped payload chunks so the parent can append directly to
        # each bucket file without waiting for the entire input to finish.
        result_queue.put(
            {
                "kind": "batch_done",
                "batch_id": batch_id,
                "rows": len(batch),
                "bucket_payloads": bucket_payloads,
                "bucket_counts": dict(bucket_counts),
                "bucket_tops": bucket_tops,
                "dropped_rows": dropped_rows,
            }
        )


def _write_progress(
    path: Path,
    *,
    input_path: Path,
    model_name: str,
    submitted_batches: int,
    completed_batches: int,
    total_rows: int,
    counts: dict[str, int],
    top_lengths: dict[str, list[int]],
    dropped_rows: int,
    start_time: float,
) -> None:
    elapsed = max(time.time() - start_time, 1e-6)
    payload = {
        "input": str(input_path),
        "model": model_name,
        "submitted_batches": submitted_batches,
        "completed_batches": completed_batches,
        "total_rows_written": total_rows,
        "dropped_rows": dropped_rows,
        "elapsed_seconds": elapsed,
        "rows_per_second": total_rows / elapsed,
        "buckets": {
            key: {
                "count": counts[key],
                "top20_lengths": top_lengths[key],
            }
            for key in counts
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Split a normalized ms-swift JSONL dataset into token-length buckets")
    parser.add_argument("input", help="Input JSONL path containing ms-swift messages-only records")
    parser.add_argument("--output-dir", required=True, help="Directory to write bucket JSONL files")
    parser.add_argument("--model", default="Qwen/Qwen3-32B", help="Tokenizer model id")
    parser.add_argument("--plan-json", default="", help="Optional bucket plan JSON path")
    parser.add_argument("--short-max", type=int, default=8192, help="Upper bound for the short bucket")
    parser.add_argument("--medium-max", type=int, default=16384, help="Upper bound for the medium bucket")
    parser.add_argument("--manifest", default="", help="Optional manifest JSON output path")
    parser.add_argument("--workers", type=int, default=16, help="Parallel tokenizer worker count")
    parser.add_argument("--batch-size", type=int, default=256, help="Records per tokenizer batch")
    parser.add_argument("--progress-path", default="", help="Optional progress JSON output path")
    parser.add_argument("--progress-interval-seconds", type=float, default=5.0, help="How often to refresh progress JSON")
    parser.add_argument(
        "--drop-unmatched",
        action="store_true",
        help="Drop rows whose token length does not match any configured stage instead of failing the split",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = Path(args.manifest) if args.manifest else output_dir / "manifest.json"
    progress_path = Path(args.progress_path) if args.progress_path else output_dir / "progress.json"

    plan = (
        json.loads(Path(args.plan_json).read_text(encoding="utf-8"))
        if args.plan_json
        else _legacy_plan(args.short_max, args.medium_max)
    )
    stages = list(plan.get("stages", []))
    if not stages:
        raise ValueError("bucket plan must contain at least one stage")
    model_name = str(plan.get("tokenizer_model") or args.model)

    bucket_paths = {
        str(stage["name"]): output_dir / str(stage.get("output_filename") or f"{_slug(str(stage['name']))}.jsonl")
        for stage in stages
    }
    bucket_files = {key: path.open("w", encoding="utf-8") for key, path in bucket_paths.items()}
    counts = {str(stage["name"]): 0 for stage in stages}
    top_lengths = {str(stage["name"]): [] for stage in stages}

    ctx = mp.get_context("spawn")
    task_queue: mp.Queue = ctx.Queue(maxsize=max(args.workers, 1) * 2)
    result_queue: mp.Queue = ctx.Queue(maxsize=max(args.workers, 1) * 2)
    workers = [
        ctx.Process(
            target=_worker,
            kwargs={
                "task_queue": task_queue,
                "result_queue": result_queue,
                "model": model_name,
                "stages": stages,
                "drop_unmatched": args.drop_unmatched,
            },
        )
        for _ in range(max(args.workers, 1))
    ]
    for proc in workers:
        proc.start()

    total = 0
    submitted_batches = 0
    completed_batches = 0
    worker_done = 0
    dropped_rows = 0
    batch: list[str] = []
    start_time = time.time()
    last_progress = 0.0

    def drain_results(*, block: bool) -> None:
        nonlocal total, completed_batches, worker_done, last_progress, dropped_rows
        while True:
            try:
                item = result_queue.get(timeout=0.2 if block else 0.0)
            except queue.Empty:
                break
            kind = item.get("kind")
            if kind == "worker_done":
                worker_done += 1
            elif kind == "batch_done":
                completed_batches += 1
                payloads = item["bucket_payloads"]
                bucket_counts = item["bucket_counts"]
                bucket_tops = item["bucket_tops"]
                dropped_rows += int(item.get("dropped_rows", 0))
                for key, payload in payloads.items():
                    if payload:
                        bucket_files[key].write(payload)
                        counts[key] += int(bucket_counts.get(key, 0))
                        total += int(bucket_counts.get(key, 0))
                    arr = top_lengths[key]
                    arr.extend(bucket_tops.get(key, []))
                    arr.sort(reverse=True)
                    del arr[20:]
            else:
                raise ValueError(f"Unknown result message: {item}")

            now = time.time()
            # ``progress.json`` is the live operator view. Keep it cheap and
            # refresh on a fixed interval rather than every completed batch.
            if now - last_progress >= max(args.progress_interval_seconds, 0.1):
                _write_progress(
                    progress_path,
                    input_path=input_path,
                    model_name=model_name,
                    submitted_batches=submitted_batches,
                    completed_batches=completed_batches,
                    total_rows=total,
                    counts=counts,
                    top_lengths=top_lengths,
                    dropped_rows=dropped_rows,
                    start_time=start_time,
                )
                last_progress = now

    with input_path.open(encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            batch.append(line)
            if len(batch) < args.batch_size:
                continue
            task_queue.put((submitted_batches, list(batch)))
            submitted_batches += 1
            batch = []
            drain_results(block=False)

        if batch:
            task_queue.put((submitted_batches, list(batch)))
            submitted_batches += 1

    for _ in workers:
        task_queue.put(None)

    while worker_done < len(workers) or completed_batches < submitted_batches:
        drain_results(block=True)

    for proc in workers:
        proc.join()
    for handle in bucket_files.values():
        handle.close()

    _write_progress(
        progress_path,
        input_path=input_path,
        model_name=model_name,
        submitted_batches=submitted_batches,
        completed_batches=completed_batches,
        total_rows=total,
        counts=counts,
        top_lengths=top_lengths,
        dropped_rows=dropped_rows,
        start_time=start_time,
    )

    manifest = {
        "input": str(input_path),
        "model": model_name,
        "total": total,
        "dropped_rows": dropped_rows,
        "buckets": {
            str(stage["name"]): {
                "path": str(bucket_paths[str(stage["name"])]),
                "count": counts[str(stage["name"])],
                "top20_lengths": top_lengths[str(stage["name"])],
                "bucket_min_length": stage.get("bucket_min_length", 0),
                "bucket_max_length": stage.get("bucket_max_length"),
                "stage_max_length": stage.get("max_length"),
            }
            for stage in stages
        },
        "plan": plan,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
