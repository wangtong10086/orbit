#!/usr/bin/env python3
"""Full fine-tuning SFT script for Qwen3-32B using HuggingFace Trainer + DeepSpeed.

v2: Supports pre-tokenized data via --pretokenized flag (loads .pt shards instantly).

Supports:
- Chat-format JSONL with messages field (and optional tools field)
- Pre-tokenized .pt shards (from pretokenize.py) — eliminates 9h tokenization bottleneck
- Dynamic padding per batch (no packing — eliminates cross-sample attention contamination)
- Length-sorted batching to minimize padding waste
- Loss only on assistant tokens
- DeepSpeed ZeRO-2/3
- Gradient checkpointing
"""

import argparse
import json
import os
import time
from typing import Dict, List, Optional

import torch
import numpy as np
from torch.utils.data import Dataset, Sampler
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
    TrainerCallback,
)
from transformers.trainer_pt_utils import LabelSmoother


def parse_args():
    parser = argparse.ArgumentParser(description="Full SFT for Qwen3-32B")
    parser.add_argument("--data_path", type=str, required=True, help="Path to JSONL training data")
    parser.add_argument("--pretokenized", type=str, default=None, help="Path to pretokenized data dir (from pretokenize.py)")
    parser.add_argument("--output_dir", type=str, required=True, help="Output directory for checkpoints")
    parser.add_argument("--model_name", type=str, default="/root/models/Qwen3-32B", help="Model name or path")
    parser.add_argument("--lr", type=float, default=2e-5, help="Learning rate")
    parser.add_argument("--epochs", type=int, default=1, help="Number of training epochs")
    parser.add_argument("--batch_size", type=int, default=2, help="Per-device batch size")
    parser.add_argument("--grad_accum", type=int, default=2, help="Gradient accumulation steps")
    parser.add_argument("--seq_len", type=int, default=32768, help="Max sequence length")
    parser.add_argument("--save_steps", type=int, default=50, help="Save checkpoint every N steps")
    parser.add_argument("--max_grad_norm", type=float, default=1.0, help="Max gradient norm")
    parser.add_argument("--warmup_ratio", type=float, default=0.03, help="Warmup ratio")
    parser.add_argument("--weight_decay", type=float, default=0.01, help="Weight decay")
    parser.add_argument("--deepspeed", type=str, default=None, help="DeepSpeed config path")
    parser.add_argument("--resume_from", type=str, default=None, help="Resume from checkpoint path")
    parser.add_argument("--local_rank", type=int, default=-1, help="Local rank for distributed training")
    return parser.parse_args()


IGNORE_TOKEN_ID = LabelSmoother.ignore_index  # -100


def detect_attn_implementation():
    """Detect best available attention implementation."""
    try:
        import flash_attn
        print(f"flash-attn {flash_attn.__version__} available, using flash_attention_2")
        return "flash_attention_2"
    except ImportError:
        print("flash-attn not available, falling back to sdpa")
        return "sdpa"


def load_jsonl(path: str) -> List[dict]:
    """Load JSONL file, one JSON object per line."""
    data = []
    with open(path, "r") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                data.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"WARNING: Skipping line {i+1}: {e}")
    return data


def tokenize_sample(sample: dict, tokenizer, max_len: int):
    """Tokenize a single sample with proper assistant-only labeling."""
    messages = sample["messages"]
    tools = sample.get("tools", None)

    full_kwargs = {"tokenize": False, "add_generation_prompt": False}
    if tools:
        full_kwargs["tools"] = tools
    full_text = tokenizer.apply_chat_template(messages, **full_kwargs)

    full_enc = tokenizer(
        full_text, truncation=True, max_length=max_len,
        add_special_tokens=False, return_tensors=None,
    )
    input_ids = full_enc["input_ids"]
    labels = [IGNORE_TOKEN_ID] * len(input_ids)

    for turn_idx, msg in enumerate(messages):
        if msg["role"] != "assistant":
            continue

        prefix_messages = messages[:turn_idx]
        prefix_kwargs = {"tokenize": False, "add_generation_prompt": True}
        if tools:
            prefix_kwargs["tools"] = tools
        if len(prefix_messages) == 0:
            prefix_text = ""
        else:
            prefix_text = tokenizer.apply_chat_template(prefix_messages, **prefix_kwargs)

        inclusive_messages = messages[:turn_idx + 1]
        inclusive_kwargs = {"tokenize": False, "add_generation_prompt": False}
        if tools:
            inclusive_kwargs["tools"] = tools
        inclusive_text = tokenizer.apply_chat_template(inclusive_messages, **inclusive_kwargs)

        if prefix_text:
            prefix_ids = tokenizer(
                prefix_text, truncation=True, max_length=max_len,
                add_special_tokens=False, return_tensors=None
            )["input_ids"]
        else:
            prefix_ids = []

        inclusive_ids = tokenizer(
            inclusive_text, truncation=True, max_length=max_len,
            add_special_tokens=False, return_tensors=None
        )["input_ids"]

        start = len(prefix_ids)
        end = min(len(inclusive_ids), len(input_ids))
        for i in range(start, end):
            labels[i] = input_ids[i]

    return input_ids, labels


class SFTDataset(Dataset):
    """Dataset supporting both raw JSONL and pre-tokenized .pt shards."""

    def __init__(self, samples: List[dict] = None, tokenizer=None, seq_len: int = 32768,
                 pretokenized_dir: str = None):
        self.data = []
        self.lengths = []

        if pretokenized_dir:
            self._load_pretokenized(pretokenized_dir)
        elif samples is not None and tokenizer is not None:
            self._tokenize_raw(samples, tokenizer, seq_len)
        else:
            raise ValueError("Either (samples, tokenizer) or pretokenized_dir required")

    def _load_pretokenized(self, pretokenized_dir: str):
        """Load pre-tokenized data from .pt shards — instant, no tokenization."""
        meta_path = os.path.join(pretokenized_dir, "meta.json")
        with open(meta_path) as f:
            meta = json.load(f)

        print(f"Loading pre-tokenized data from {pretokenized_dir}")
        print(f"  Source: {meta.get('source', 'unknown')}")
        print(f"  Samples: {meta['total_samples']:,}")
        print(f"  Tokens: {meta['total_tokens']:,}")
        print(f"  Assistant tokens: {meta['total_assistant_tokens']:,} "
              f"({meta['total_assistant_tokens']/max(meta['total_tokens'],1)*100:.1f}%)")

        t0 = time.time()
        shard_files = sorted([f for f in os.listdir(pretokenized_dir) if f.endswith('.pt')])
        for shard_file in shard_files:
            shard_path = os.path.join(pretokenized_dir, shard_file)
            shard_data = torch.load(shard_path, weights_only=False)
            for item in shard_data:
                self.data.append((item["input_ids"], item["labels"]))
                self.lengths.append(item["length"])

        elapsed = time.time() - t0
        print(f"  Loaded {len(self.data)} samples from {len(shard_files)} shards in {elapsed:.1f}s")

        if self.lengths:
            lengths_arr = np.array(self.lengths)
            print(f"  Length stats: min={lengths_arr.min()}, median={int(np.median(lengths_arr))}, "
                  f"mean={lengths_arr.mean():.0f}, p95={int(np.percentile(lengths_arr, 95))}, "
                  f"max={lengths_arr.max()}")

    def _tokenize_raw(self, samples, tokenizer, seq_len):
        """Tokenize raw samples — slow, use pretokenized when possible."""
        print(f"Tokenizing {len(samples)} samples (consider using pretokenize.py for speed)...")
        skipped = 0
        total_assistant_tokens = 0
        total_tokens = 0

        for i, sample in enumerate(samples):
            if i % 500 == 0 and i > 0:
                print(f"  Tokenized {i}/{len(samples)}...")
            try:
                input_ids, labels = tokenize_sample(sample, tokenizer, seq_len)
                if len(input_ids) > 0:
                    self.data.append((input_ids, labels))
                    self.lengths.append(len(input_ids))
                    total_tokens += len(input_ids)
                    total_assistant_tokens += sum(1 for l in labels if l != IGNORE_TOKEN_ID)
            except Exception as e:
                skipped += 1
                if skipped <= 10:
                    print(f"  WARNING: Skipping sample {i}: {e}")

        if skipped > 0:
            print(f"  Skipped {skipped} samples due to errors")

        print(f"Dataset: {len(self.data)} samples, {total_tokens:,} tokens, "
              f"{total_assistant_tokens:,} assistant ({total_assistant_tokens/max(total_tokens,1)*100:.1f}%)")

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        input_ids, labels = self.data[idx]
        return {
            "input_ids": input_ids,
            "labels": labels,
            "length": len(input_ids),
        }


class DataCollatorDynamicPad:
    """Pads each batch to the max length within that batch."""

    def __init__(self, pad_token_id: int):
        self.pad_token_id = pad_token_id

    def __call__(self, features: List[dict]) -> dict:
        max_len = max(len(f["input_ids"]) for f in features)

        batch_input_ids = []
        batch_labels = []
        batch_attention_mask = []

        for f in features:
            ids = f["input_ids"]
            lbls = f["labels"]
            seq_len = len(ids)
            pad_len = max_len - seq_len

            batch_input_ids.append(ids + [self.pad_token_id] * pad_len)
            batch_labels.append(lbls + [IGNORE_TOKEN_ID] * pad_len)
            batch_attention_mask.append([1] * seq_len + [0] * pad_len)

        return {
            "input_ids": torch.tensor(batch_input_ids, dtype=torch.long),
            "labels": torch.tensor(batch_labels, dtype=torch.long),
            "attention_mask": torch.tensor(batch_attention_mask, dtype=torch.long),
        }


class LengthGroupedSampler(Sampler):
    """Groups samples by length to minimize padding waste."""

    def __init__(self, lengths: List[int], batch_size: int, world_size: int = 1, rank: int = 0, seed: int = 42):
        self.batch_size = batch_size
        self.world_size = world_size
        self.rank = rank

        self.sorted_indices = sorted(range(len(lengths)), key=lambda i: lengths[i])

        mega_batch_size = batch_size * 100
        shuffled = []
        rng = np.random.RandomState(seed)
        for i in range(0, len(self.sorted_indices), mega_batch_size):
            group = self.sorted_indices[i : i + mega_batch_size]
            rng.shuffle(group)
            shuffled.extend(group)
        self.sorted_indices = shuffled

    def __iter__(self):
        indices = self.sorted_indices[self.rank :: self.world_size]
        return iter(indices)

    def __len__(self):
        return len(self.sorted_indices) // self.world_size + (
            1 if self.rank < len(self.sorted_indices) % self.world_size else 0
        )


class ThroughputCallback(TrainerCallback):
    """Logs training metrics every N steps."""

    def __init__(self, log_every=10, num_gpus=8):
        self.log_every = log_every
        self.num_gpus = num_gpus
        self.start_time = None
        self.last_log_time = None
        self.last_log_step = 0

    def on_train_begin(self, args, state, control, **kwargs):
        self.start_time = time.time()
        self.last_log_time = time.time()

    def on_log(self, args, state, control, logs=None, **kwargs):
        if logs is None or state.global_step == 0:
            return
        if state.global_step % self.log_every != 0:
            return

        rank = int(os.environ.get("LOCAL_RANK", 0))
        if rank != 0:
            return

        now = time.time()
        elapsed = now - self.start_time
        interval = now - self.last_log_time
        steps_in_interval = state.global_step - self.last_log_step

        loss = logs.get("loss", 0)
        lr = logs.get("learning_rate", 0)

        if steps_in_interval > 0 and interval > 0:
            sec_per_step = interval / steps_in_interval
        else:
            sec_per_step = 0

        print(
            f"[Step {state.global_step:>5d}/{state.max_steps}] "
            f"loss={loss:.4f}  lr={lr:.2e}  "
            f"{sec_per_step:.1f}s/step  "
            f"elapsed={elapsed:.0f}s"
        )

        self.last_log_time = now
        self.last_log_step = state.global_step


def main():
    args = parse_args()

    rank = int(os.environ.get("LOCAL_RANK", 0))
    world_size = int(os.environ.get("WORLD_SIZE", 1))

    if rank == 0:
        print("=" * 60)
        print("Full Fine-Tuning SFT — Dynamic Padding (no packing)")
        print("=" * 60)
        for k, v in vars(args).items():
            print(f"  {k}: {v}")
        print("=" * 60)

    # Load tokenizer
    if rank == 0:
        print("Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(
        args.model_name, trust_remote_code=True, padding_side="right",
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        tokenizer.pad_token_id = tokenizer.eos_token_id

    # Load data — pretokenized (fast) or raw JSONL (slow)
    if args.pretokenized:
        dataset = SFTDataset(pretokenized_dir=args.pretokenized)
    else:
        if rank == 0:
            print(f"Loading data from {args.data_path}...")
        raw_data = load_jsonl(args.data_path)
        if rank == 0:
            print(f"Loaded {len(raw_data)} samples")
        dataset = SFTDataset(raw_data, tokenizer, args.seq_len)

    if rank == 0:
        print(f"Dataset ready: {len(dataset)} samples")

    # Create length-grouped sampler
    sampler = LengthGroupedSampler(
        lengths=dataset.lengths,
        batch_size=args.batch_size,
        world_size=world_size,
        rank=rank,
        seed=42,
    )

    collator = DataCollatorDynamicPad(pad_token_id=tokenizer.pad_token_id)

    # Detect attention implementation
    attn_impl = detect_attn_implementation()

    # Load model
    if rank == 0:
        print(f"Loading model {args.model_name}...")
    model = AutoModelForCausalLM.from_pretrained(
        args.model_name,
        torch_dtype=torch.bfloat16,
        trust_remote_code=True,
        attn_implementation=attn_impl,
    )
    model.config.use_cache = False

    if rank == 0:
        total_params = sum(p.numel() for p in model.parameters())
        trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
        print(f"Model parameters: {total_params/1e9:.1f}B total, {trainable_params/1e9:.1f}B trainable")

    # Training arguments
    training_args = TrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        weight_decay=args.weight_decay,
        warmup_ratio=args.warmup_ratio,
        max_grad_norm=args.max_grad_norm,
        bf16=True,
        logging_steps=10,
        save_steps=args.save_steps,
        save_total_limit=5,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        deepspeed=args.deepspeed,
        report_to="wandb" if os.environ.get("WANDB_API_KEY") else "none",
        run_name="qwen3-32b-full-sft",
        dataloader_num_workers=4,
        dataloader_pin_memory=True,
        remove_unused_columns=False,
        lr_scheduler_type="cosine",
        seed=42,
    )

    num_gpus = int(os.environ.get("WORLD_SIZE", torch.cuda.device_count()))

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        data_collator=collator,
        callbacks=[ThroughputCallback(log_every=10, num_gpus=num_gpus)],
    )

    def get_train_dataloader_custom():
        from torch.utils.data import DataLoader
        return DataLoader(
            dataset,
            batch_size=training_args.per_device_train_batch_size,
            sampler=sampler,
            collate_fn=collator,
            num_workers=training_args.dataloader_num_workers,
            pin_memory=training_args.dataloader_pin_memory,
            drop_last=True,
        )

    trainer.get_train_dataloader = get_train_dataloader_custom

    if rank == 0:
        if args.resume_from:
            print(f"Resuming training from {args.resume_from}...")
        else:
            print("Starting training...")
    trainer.train(resume_from_checkpoint=args.resume_from)

    if rank == 0:
        print("Saving final model...")
    trainer.save_model(os.path.join(args.output_dir, "final"))
    tokenizer.save_pretrained(os.path.join(args.output_dir, "final"))

    if rank == 0:
        print("Training complete!")


if __name__ == "__main__":
    main()
