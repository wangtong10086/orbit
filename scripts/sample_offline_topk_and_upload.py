#!/usr/bin/env python3
"""Run offline-topk sampling, validate the output, and upload it to HF."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from orbit.config import load_dotenv
from orbit.data.offline_topk_ops import (
    filter_messages_jsonl_by_max_length,
    upload_offline_topk_jsonl,
    validate_offline_topk_jsonl,
)


def _bool_arg(value: bool) -> str:
    return "true" if value else "false"


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Sample offline-topk teacher data and upload it to Hugging Face")
    parser.add_argument("--model", required=True, help="Student tokenizer/model family used for response_token_ids")
    parser.add_argument("--dataset", required=True, help="Input messages-only JSONL path")
    parser.add_argument("--output-dir", required=True, help="Directory for sampled output")
    parser.add_argument("--output-file", default="offline_topk.jsonl", help="Sampled JSONL filename")
    parser.add_argument("--gkd-logits-topk", type=int, required=True, help="Teacher top-k width")
    parser.add_argument("--teacher-model", default="", help="Local teacher model id")
    parser.add_argument("--teacher-model-server", default="", help="OpenAI-compatible teacher server URL")
    parser.add_argument("--use-hf", action="store_true", help="Pass --use_hf true to swift sample")
    parser.add_argument("--num-sampling-batch-size", type=int, default=1)
    parser.add_argument("--num-sampling-batches", type=int, default=0, help="0 means let swift sample process the full dataset")
    parser.add_argument("--hf-repo", default="", help="HF dataset repo id for upload")
    parser.add_argument("--hf-path", default="", help="Target path inside the HF dataset repo")
    parser.add_argument("--create-repo", action="store_true", help="Create the HF dataset repo if missing")
    parser.add_argument("--public", action="store_true", help="Create the dataset repo as public instead of private")
    parser.add_argument(
        "--filter-max-length",
        type=int,
        default=0,
        help="If > 0, filter out messages rows whose tokenized length exceeds this value before sampling",
    )
    args = parser.parse_args()

    teacher_model = args.teacher_model.strip()
    teacher_server = args.teacher_model_server.strip()
    hf_repo = args.hf_repo.strip() or os.environ.get("HF_DATASET_REPO", "").strip()
    if bool(teacher_model) == bool(teacher_server):
        raise SystemExit("Exactly one of --teacher-model or --teacher-model-server is required")
    if not hf_repo:
        raise SystemExit("--hf-repo is required or set HF_DATASET_REPO")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / args.output_file
    dataset_path = Path(args.dataset)
    filter_summary = None
    if args.filter_max_length > 0:
        filtered_path = output_dir / f"{dataset_path.stem}.le{args.filter_max_length}.jsonl"
        filter_summary = filter_messages_jsonl_by_max_length(
            path=dataset_path,
            output_path=filtered_path,
            model=args.model,
            max_length=args.filter_max_length,
        )
        dataset_path = filtered_path

    command = [
        sys.executable,
        "-m",
        "swift.cli.main",
        "sample",
        "--model",
        args.model,
        "--sampler_type",
        "gkd_topk",
        "--gkd_logits_topk",
        str(args.gkd_logits_topk),
        "--dataset",
        str(dataset_path),
        "--output_dir",
        str(output_dir),
        "--output_file",
        args.output_file,
        "--num_sampling_batch_size",
        str(args.num_sampling_batch_size),
    ]
    if args.use_hf:
        command.extend(["--use_hf", "true"])
    if args.num_sampling_batches > 0:
        command.extend(["--num_sampling_batches", str(args.num_sampling_batches)])
    if teacher_model:
        command.extend(["--teacher_model", teacher_model])
    else:
        command.extend(["--teacher_model_server", teacher_server])

    subprocess.run(command, check=True)

    summary = validate_offline_topk_jsonl(output_path)
    upload = upload_offline_topk_jsonl(
        path=output_path,
        repo_id=hf_repo,
        path_in_repo=args.hf_path,
        create_repo=args.create_repo,
        private=not args.public,
    )

    print(
        {
            "sampled_file": str(output_path),
            "filtered_dataset": filter_summary,
            "validation": summary,
            "upload": upload,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
