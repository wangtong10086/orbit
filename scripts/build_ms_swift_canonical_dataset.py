#!/usr/bin/env python3
"""Build a normalized ms-swift dataset from canonical JSONL files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from orbit.data.ms_swift_dataset import build_ms_swift_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a normalized ms-swift JSONL dataset from canonical files")
    parser.add_argument("inputs", nargs="+", help="Input canonical JSONL files")
    parser.add_argument("-o", "--output", required=True, help="Output JSONL path")
    parser.add_argument("--manifest", default="", help="Optional manifest JSON path")
    args = parser.parse_args()

    report = build_ms_swift_dataset(
        input_paths=args.inputs,
        output_path=args.output,
        manifest_path=args.manifest or None,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
