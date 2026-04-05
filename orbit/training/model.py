"""Model management — load, merge LoRA, upload to HuggingFace.

Extracted from deploy.py for clean separation of concerns.
"""

from __future__ import annotations

import os
from typing import Optional


def merge_lora_adapter(
    base_model: str,
    adapter_path: str,
    output_path: str,
    push_to_hub: Optional[str] = None,
    hf_token: Optional[str] = None,
) -> str:
    """Merge LoRA adapter into base model and save.

    Args:
        base_model: Base model name/path (e.g. "Qwen/Qwen3-32B")
        adapter_path: Path to LoRA adapter (local or HF repo)
        output_path: Where to save merged model
        push_to_hub: Optional HF repo to push merged model
        hf_token: HuggingFace token

    Returns:
        Path to merged model (local or HF repo)
    """
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel
    import torch

    print(f"Loading base model: {base_model}")
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        token=hf_token,
        trust_remote_code=False,
    )
    tokenizer = AutoTokenizer.from_pretrained(
        base_model,
        token=hf_token,
        trust_remote_code=False,
    )

    print(f"Loading LoRA adapter: {adapter_path}")
    model = PeftModel.from_pretrained(model, adapter_path, token=hf_token)

    print("Merging weights...")
    model = model.merge_and_unload()

    print(f"Saving to {output_path}")
    os.makedirs(output_path, exist_ok=True)
    model.save_pretrained(output_path, safe_serialization=True)
    tokenizer.save_pretrained(output_path)

    if push_to_hub:
        print(f"Pushing to HuggingFace: {push_to_hub}")
        model.push_to_hub(push_to_hub, token=hf_token, safe_serialization=True)
        tokenizer.push_to_hub(push_to_hub, token=hf_token)
        return push_to_hub

    return output_path


def get_hf_latest_revision(repo_id: str, hf_token: str) -> str:
    """Get the latest commit SHA from a HuggingFace repo."""
    from huggingface_hub import HfApi
    api = HfApi(token=hf_token)
    info = api.repo_info(repo_id, repo_type="model", token=hf_token)
    return info.sha
