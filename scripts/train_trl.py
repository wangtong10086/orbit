#!/usr/bin/env python3
"""Full fine-tuning with TRL SFTTrainer + DeepSpeed ZeRO-3.

Supports OpenAI multi-turn tool calling natively:
  user → assistant(tool_calls) → tool → assistant(tool_calls) → tool → assistant

Usage:
  deepspeed --num_gpus=8 train_trl.py --data /data/datasets/combined.jsonl --model /data/models/Qwen3-32B
"""

import argparse
import json
import os

import torch
from datasets import Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import SFTConfig, SFTTrainer


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="JSONL training data path")
    parser.add_argument("--model", default="/data/models/Qwen3-32B", help="Model path")
    parser.add_argument("--output", default="/data/checkpoints", help="Output dir")
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch_size", type=int, default=1)
    parser.add_argument("--grad_accum", type=int, default=4)
    parser.add_argument("--seq_len", type=int, default=32768)
    parser.add_argument("--save_steps", type=int, default=100)
    parser.add_argument("--save_limit", type=int, default=5)
    parser.add_argument("--deepspeed", default=None, help="DeepSpeed config path")
    parser.add_argument("--local_rank", type=int, default=-1)
    return parser.parse_args()


def load_jsonl(path):
    """Load JSONL, keeping messages and tools fields."""
    data = []
    skipped = 0
    with open(path) as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                msgs = d.get("messages", [])
                if not msgs:
                    skipped += 1
                    continue
                # Ensure last message is assistant
                if msgs[-1].get("role") != "assistant":
                    skipped += 1
                    continue
                entry = {"messages": msgs}
                if d.get("tools"):
                    entry["tools"] = d["tools"]
                data.append(entry)
            except json.JSONDecodeError:
                skipped += 1
    return data, skipped


def main():
    args = parse_args()
    rank = int(os.environ.get("LOCAL_RANK", 0))

    if rank == 0:
        print("=" * 60)
        print("TRL SFTTrainer — Full Fine-Tuning + DeepSpeed ZeRO-3")
        print("=" * 60)
        for k, v in vars(args).items():
            print(f"  {k}: {v}")
        print("=" * 60)

    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Load data
    if rank == 0:
        print(f"Loading data from {args.data}...")
    raw_data, skipped = load_jsonl(args.data)
    if rank == 0:
        print(f"  Loaded: {len(raw_data)} samples (skipped {skipped})")

    dataset = Dataset.from_list(raw_data)

    # Training config
    training_args = SFTConfig(
        output_dir=args.output,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        weight_decay=0.01,
        max_grad_norm=1.0,
        max_length=args.seq_len,
        bf16=True,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        logging_steps=10,
        save_steps=args.save_steps,
        save_total_limit=args.save_limit,
        deepspeed=args.deepspeed,
        report_to="none",
        seed=42,
        dataloader_num_workers=4,
        dataloader_pin_memory=True,
    )

    # Load model
    if rank == 0:
        print(f"Loading model {args.model}...")

    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        torch_dtype=torch.bfloat16,
        trust_remote_code=True,
        attn_implementation="sdpa",
    )
    model.config.use_cache = False

    if rank == 0:
        params = sum(p.numel() for p in model.parameters())
        print(f"  Parameters: {params/1e9:.1f}B")

    # Trainer — TRL handles chat template + loss masking automatically
    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        processing_class=tokenizer,
    )

    if rank == 0:
        print("Starting training...")
    trainer.train()

    if rank == 0:
        print("Saving final model...")
    trainer.save_model(os.path.join(args.output, "final"))
    tokenizer.save_pretrained(os.path.join(args.output, "final"))

    if rank == 0:
        print("Training complete!")


if __name__ == "__main__":
    main()
