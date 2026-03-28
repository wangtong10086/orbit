#!/usr/bin/env python3
"""Pre-tokenize JSONL data for Full FT training.

Uses subprocess parallelism (not multiprocessing.Pool) to avoid fork/spawn issues.
Each worker is an independent process tokenizing a slice of the data.

Usage:
    python3 pretokenize.py --data /root/data/combined.jsonl --model /root/models/Qwen3-32B --seq-len 32768 --workers 16
"""

import argparse
import json
import os
import subprocess
import sys
import time


def worker_main():
    """Entry point for worker subprocess. Reads args from sys.argv."""
    import numpy as np
    from transformers import AutoTokenizer
    from transformers.trainer_pt_utils import LabelSmoother
    IGNORE = LabelSmoother.ignore_index

    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--data", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--seq-len", type=int, required=True)
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--worker-id", type=int, required=True)
    args = parser.parse_args()

    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True, padding_side="right")
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        tokenizer.pad_token_id = tokenizer.eos_token_id

    # Load only our slice
    data = []
    with open(args.data) as f:
        for i, line in enumerate(f):
            if i < args.start:
                continue
            if i >= args.end:
                break
            line = line.strip()
            if line:
                try:
                    data.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    results = []
    t0 = time.time()
    for idx, sample in enumerate(data):
        messages = sample["messages"]
        tools = sample.get("tools", None)

        full_kwargs = {"tokenize": False, "add_generation_prompt": False}
        if tools:
            full_kwargs["tools"] = tools
        full_text = tokenizer.apply_chat_template(messages, **full_kwargs)
        full_enc = tokenizer(full_text, truncation=True, max_length=args.seq_len,
                             add_special_tokens=False, return_tensors=None)
        input_ids = full_enc["input_ids"]
        labels = [IGNORE] * len(input_ids)

        for turn_idx, msg in enumerate(messages):
            if msg["role"] != "assistant":
                continue
            prefix_messages = messages[:turn_idx]
            prefix_kwargs = {"tokenize": False, "add_generation_prompt": True}
            if tools:
                prefix_kwargs["tools"] = tools
            prefix_text = tokenizer.apply_chat_template(prefix_messages, **prefix_kwargs) if prefix_messages else ""

            inclusive_messages = messages[:turn_idx + 1]
            inclusive_kwargs = {"tokenize": False, "add_generation_prompt": False}
            if tools:
                inclusive_kwargs["tools"] = tools
            inclusive_text = tokenizer.apply_chat_template(inclusive_messages, **inclusive_kwargs)

            prefix_ids = tokenizer(prefix_text, truncation=True, max_length=args.seq_len,
                                   add_special_tokens=False, return_tensors=None)["input_ids"] if prefix_text else []
            inclusive_ids = tokenizer(inclusive_text, truncation=True, max_length=args.seq_len,
                                     add_special_tokens=False, return_tensors=None)["input_ids"]

            start_pos = len(prefix_ids)
            end_pos = min(len(inclusive_ids), len(input_ids))
            for i in range(start_pos, end_pos):
                labels[i] = input_ids[i]

        if len(input_ids) > 0:
            results.append({"input_ids": input_ids, "labels": labels, "length": len(input_ids)})

        if (idx + 1) % 200 == 0:
            elapsed = time.time() - t0
            rate = (idx + 1) / elapsed
            print(f"  [W{args.worker_id}] {idx+1}/{len(data)} ({rate:.1f}/s)", flush=True)

    # Save results as JSON (avoid torch import in workers)
    with open(args.output, "w") as f:
        json.dump(results, f)
    elapsed = time.time() - t0
    print(f"  [W{args.worker_id}] Done: {len(results)} samples in {elapsed:.0f}s", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Pre-tokenize JSONL for Full FT")
    parser.add_argument("--worker", action="store_true", help="Run as worker subprocess")
    parser.add_argument("--data", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--seq-len", type=int, default=32768)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--output", default=None)

    # Worker-only args
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=0)
    parser.add_argument("--worker-id", type=int, default=0)

    args = parser.parse_args()

    if args.worker:
        worker_main()
        return

    # Main process: count lines, split, launch workers, merge
    output_dir = args.output or args.data.replace(".jsonl", "_tokenized")
    os.makedirs(output_dir, exist_ok=True)
    tmp_dir = os.path.join(output_dir, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    # Count lines
    print(f"Counting lines in {args.data}...")
    with open(args.data) as f:
        total_lines = sum(1 for _ in f)
    print(f"Total: {total_lines} lines")

    # Split into worker ranges
    chunk_size = (total_lines + args.workers - 1) // args.workers
    workers = []
    t0 = time.time()

    print(f"Launching {args.workers} workers...")
    for w in range(args.workers):
        start = w * chunk_size
        end = min(start + chunk_size, total_lines)
        if start >= total_lines:
            break
        out_path = os.path.join(tmp_dir, f"worker_{w:03d}.json")
        cmd = [
            sys.executable, __file__, "--worker",
            "--data", args.data,
            "--model", args.model,
            "--seq-len", str(args.seq_len),
            "--start", str(start),
            "--end", str(end),
            "--output", out_path,
            "--worker-id", str(w),
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        workers.append((w, proc, out_path, end - start))
        print(f"  W{w}: lines {start}-{end} ({end-start} samples)")

    # Wait for all workers, streaming output
    print(f"\nWaiting for {len(workers)} workers...")
    for w_id, proc, out_path, count in workers:
        stdout, _ = proc.communicate()
        if stdout:
            print(stdout.decode(), end="")
        if proc.returncode != 0:
            print(f"ERROR: Worker {w_id} failed with exit code {proc.returncode}")

    elapsed = time.time() - t0
    print(f"\nAll workers done in {elapsed:.0f}s")

    # Merge results
    print("Merging results...")
    import torch
    import numpy as np

    all_results = []
    total_tokens = 0
    total_asst = 0
    for w_id, _, out_path, _ in workers:
        if not os.path.exists(out_path):
            print(f"  WARNING: Missing output from worker {w_id}")
            continue
        with open(out_path) as f:
            shard = json.load(f)
        for r in shard:
            total_tokens += r["length"]
            total_asst += sum(1 for l in r["labels"] if l != -100)
        all_results.extend(shard)
        os.remove(out_path)  # cleanup tmp

    print(f"Total: {len(all_results)} samples, {total_tokens:,} tokens, "
          f"{total_asst:,} assistant tokens ({total_asst/max(total_tokens,1)*100:.1f}%)")

    lengths = [r["length"] for r in all_results]
    lengths_arr = np.array(lengths)
    print(f"Length stats: min={lengths_arr.min()}, median={int(np.median(lengths_arr))}, "
          f"mean={lengths_arr.mean():.0f}, p95={int(np.percentile(lengths_arr, 95))}, max={lengths_arr.max()}")

    # Save as shards
    shard_size = 5000
    num_shards = (len(all_results) + shard_size - 1) // shard_size
    print(f"\nSaving {num_shards} shards...")
    for s in range(num_shards):
        start = s * shard_size
        end = min(start + shard_size, len(all_results))
        torch.save(all_results[start:end], os.path.join(output_dir, f"shard_{s:04d}.pt"))
        print(f"  Shard {s}: {end-start} samples")

    meta = {
        "total_samples": len(all_results),
        "total_tokens": total_tokens,
        "total_assistant_tokens": total_asst,
        "seq_len": args.seq_len,
        "num_shards": num_shards,
        "model": args.model,
        "source": args.data,
    }
    with open(os.path.join(output_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    # Cleanup tmp dir
    os.rmdir(tmp_dir)
    print(f"\nDone! Total time: {time.time()-t0:.0f}s")
    print(f"Output: {output_dir}/")


if __name__ == "__main__":
    main()
