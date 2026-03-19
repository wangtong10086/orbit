#!/usr/bin/env python3
"""Merge LoRA adapter with base model for deployment."""

import sys
import os
import torch
from pathlib import Path

def main():
    adapter_path = sys.argv[1] if len(sys.argv) > 1 else "/root/checkpoints/checkpoint-287"
    output_path = sys.argv[2] if len(sys.argv) > 2 else "/root/merged_model"
    base_model = "Qwen/Qwen3-32B"

    # Find the latest checkpoint if default doesn't exist
    if not os.path.exists(adapter_path):
        ckpt_dir = Path("/root/checkpoints")
        ckpts = sorted(ckpt_dir.glob("checkpoint-*"), key=lambda p: int(p.name.split("-")[1]))
        if ckpts:
            adapter_path = str(ckpts[-1])
            print(f"Using latest checkpoint: {adapter_path}")
        else:
            print("No checkpoints found!")
            sys.exit(1)

    print(f"=== LoRA Merge ===")
    print(f"Base model: {base_model}")
    print(f"Adapter:    {adapter_path}")
    print(f"Output:     {output_path}")

    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    print("Loading base model (bf16)...")
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=False,
    )
    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=False)

    print("Loading LoRA adapter...")
    model = PeftModel.from_pretrained(model, adapter_path)

    print("Merging weights...")
    model = model.merge_and_unload()

    print(f"Saving merged model to {output_path}...")
    os.makedirs(output_path, exist_ok=True)
    model.save_pretrained(output_path)
    tokenizer.save_pretrained(output_path)

    print(f"Done! Merged model saved to {output_path}")

if __name__ == "__main__":
    main()
