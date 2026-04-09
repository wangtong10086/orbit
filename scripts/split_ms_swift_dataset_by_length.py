#!/usr/bin/env python3
"""Split a normalized ms-swift JSONL dataset into token-length buckets."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path
import re

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
        _TOKENIZER = AutoTokenizer.from_pretrained(model, trust_remote_code=True)
    return _TOKENIZER


def _process_batch(batch: list[str], *, model: str, stages: list[dict]) -> tuple[dict[str, list[str]], Counter, dict[str, list[int]]]:
    tok = _get_tokenizer(model)
    bucketed_lines: dict[str, list[str]] = {str(stage["name"]): [] for stage in stages}
    counts: Counter = Counter()
    tops: dict[str, list[int]] = {key: [] for key in bucketed_lines}

    for line in batch:
        row = json.loads(line)
        messages = row["messages"]
        length = len(tok.apply_chat_template(messages, tokenize=True, add_generation_prompt=False))
        bucket = _bucket_name(length, stages)
        bucketed_lines[bucket].append(line)
        counts[bucket] += 1
        arr = tops[bucket]
        arr.append(length)
        arr.sort(reverse=True)
        del arr[20:]
    return bucketed_lines, counts, tops


def main() -> int:
    parser = argparse.ArgumentParser(description="Split a normalized ms-swift JSONL dataset into token-length buckets")
    parser.add_argument("input", help="Input JSONL path containing ms-swift messages-only records")
    parser.add_argument("--output-dir", required=True, help="Directory to write bucket JSONL files")
    parser.add_argument("--model", default="Qwen/Qwen3-32B", help="Tokenizer model id")
    parser.add_argument("--plan-json", default="", help="Optional bucket plan JSON path")
    parser.add_argument("--short-max", type=int, default=8192, help="Upper bound for the short bucket")
    parser.add_argument("--medium-max", type=int, default=16384, help="Upper bound for the medium bucket")
    parser.add_argument("--manifest", default="", help="Optional manifest JSON output path")
    parser.add_argument("--workers", type=int, default=8, help="Parallel tokenizer worker count")
    parser.add_argument("--batch-size", type=int, default=64, help="Records per tokenizer batch")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = Path(args.manifest) if args.manifest else output_dir / "manifest.json"

    plan = (
        json.loads(Path(args.plan_json).read_text(encoding="utf-8"))
        if args.plan_json
        else _legacy_plan(args.short_max, args.medium_max)
    )
    stages = list(plan.get("stages", []))
    if not stages:
        raise ValueError("bucket plan must contain at least one stage")
    model_name = str(plan.get("tokenizer_model") or args.model)

    bucket_files = {
        str(stage["name"]): (output_dir / str(stage.get("output_filename") or f"{_slug(str(stage['name']))}.jsonl")).open(
            "w", encoding="utf-8"
        )
        for stage in stages
    }
    counts = {str(stage["name"]): 0 for stage in stages}
    top_lengths = {str(stage["name"]): [] for stage in stages}

    total = 0
    with input_path.open(encoding="utf-8") as handle, ProcessPoolExecutor(max_workers=max(args.workers, 1)) as pool:
        pending = []
        batch: list[str] = []

        def submit_current() -> None:
            nonlocal batch
            if not batch:
                return
            pending.append(
                pool.submit(
                    _process_batch,
                    list(batch),
                    model=model_name,
                    stages=stages,
                )
            )
            batch = []

        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            batch.append(line)
            if len(batch) >= args.batch_size:
                submit_current()
                if len(pending) >= max(args.workers, 1) * 4:
                    done = next(as_completed(pending))
                    bucketed_lines, bucket_counts, bucket_tops = done.result()
                    pending.remove(done)
                    for key, rows in bucketed_lines.items():
                        if rows:
                            bucket_files[key].write("\n".join(rows) + "\n")
                            counts[key] += len(rows)
                            total += len(rows)
                        arr = top_lengths[key]
                        arr.extend(bucket_tops[key])
                        arr.sort(reverse=True)
                        del arr[20:]

        submit_current()
        for done in as_completed(pending):
            bucketed_lines, bucket_counts, bucket_tops = done.result()
            for key, rows in bucketed_lines.items():
                if rows:
                    bucket_files[key].write("\n".join(rows) + "\n")
                    counts[key] += len(rows)
                    total += len(rows)
                arr = top_lengths[key]
                arr.extend(bucket_tops[key])
                arr.sort(reverse=True)
                del arr[20:]

    for handle in bucket_files.values():
        handle.close()

    manifest = {
        "input": str(input_path),
        "model": model_name,
        "total": total,
        "buckets": {
            str(stage["name"]): {
                "path": str(output_dir / str(stage.get("output_filename") or f"{_slug(str(stage['name']))}.jsonl")),
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
