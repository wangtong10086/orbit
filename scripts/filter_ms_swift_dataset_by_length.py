#!/usr/bin/env python3
"""Filter a normalized ms-swift messages JSONL dataset by max token length."""

from __future__ import annotations

import argparse
import json

from orbit.data.offline_topk_ops import filter_messages_jsonl_by_max_length


def main() -> int:
    parser = argparse.ArgumentParser(description="Filter a messages-only JSONL dataset by token length")
    parser.add_argument("input", help="Input messages-only JSONL path")
    parser.add_argument("--output", required=True, help="Filtered JSONL output path")
    parser.add_argument("--model", default="Qwen/Qwen3-32B", help="Tokenizer model id")
    parser.add_argument("--max-length", type=int, required=True, help="Maximum allowed token length")
    args = parser.parse_args()

    report = filter_messages_jsonl_by_max_length(
        path=args.input,
        output_path=args.output,
        model=args.model,
        max_length=args.max_length,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
