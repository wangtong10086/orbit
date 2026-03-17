"""Model deployment pipeline: merge LoRA → HuggingFace → Chutes → chain commit."""

import os
import json
import tempfile
from pathlib import Path
from typing import Optional

from forge.config import ForgeConfig


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


def generate_chutes_config(
    hf_repo: str,
    revision: str = "main",
    chute_name: Optional[str] = None,
    gpu_count: int = 4,
    username: str = "",
) -> str:
    """Generate Chutes deployment Python file content.

    Based on affine-cortex miner deployment template.

    Args:
        hf_repo: HuggingFace model repository
        revision: Model revision/commit SHA
        chute_name: Optional chute name override
        gpu_count: Number of GPUs
        username: Chutes username (defaults to CHUTES_USERNAME env var)
    """
    name = chute_name or hf_repo.split("/")[-1]
    chutes_username = username or os.environ.get("CHUTES_USERNAME", "")

    return f'''"""Auto-generated Chutes deployment for {hf_repo}."""
from chutes.chute import NodeSelector
from chutes.chute.template.sglang import build_sglang_chute

chute = build_sglang_chute(
    username="{chutes_username}",
    readme="{hf_repo}",
    model_name="{hf_repo}",
    image="chutes/sglang:nightly-2025081600",
    concurrency=40,
    revision="{revision}",
    node_selector=NodeSelector(
        gpu_count={gpu_count},
        include=["h200"],
    ),
    scaling_threshold=0.5,
    max_instances=2,
    shutdown_after_seconds=28800,
)
'''


def get_hf_latest_revision(repo_id: str, hf_token: str) -> str:
    """Get the latest commit SHA from a HuggingFace repo."""
    from huggingface_hub import HfApi
    api = HfApi(token=hf_token)
    info = api.repo_info(repo_id, repo_type="model", token=hf_token)
    return info.sha


class DeployPipeline:
    """Full deployment pipeline."""

    def __init__(self, config: ForgeConfig):
        self.config = config

    def merge_and_upload(
        self,
        adapter_source: str,
        deploy_repo: str,
        base_model: str = "Qwen/Qwen3-32B",
    ) -> str:
        """Merge LoRA adapter and upload to HuggingFace.

        Args:
            adapter_source: LoRA adapter path (local dir or HF repo)
            deploy_repo: Target HF repo for merged model
            base_model: Base model name

        Returns:
            HF revision SHA
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            merged_path = os.path.join(tmpdir, "merged")
            merge_lora_adapter(
                base_model=base_model,
                adapter_path=adapter_source,
                output_path=merged_path,
                push_to_hub=deploy_repo,
                hf_token=self.config.hf_token,
            )

        revision = get_hf_latest_revision(deploy_repo, self.config.hf_token)
        print(f"Merged model uploaded: {deploy_repo} @ {revision[:12]}")
        return revision

    def generate_deploy_script(self, hf_repo: str, revision: str) -> str:
        """Generate and save Chutes deployment script."""
        content = generate_chutes_config(hf_repo, revision)
        script_path = str(self.config.project_root / "tmp_chute.py")
        with open(script_path, "w") as f:
            f.write(content)
        print(f"Chutes config written: {script_path}")
        print(f"\nTo deploy manually:")
        print(f"  pip install chutes")
        print(f"  chutes deploy {script_path}:chute --accept-fee")
        return script_path

    def print_commit_command(self, hf_repo: str, revision: str, chute_id: str = "<CHUTE_ID>"):
        """Print the chain commit command."""
        print(f"\nTo commit on chain:")
        print(f"  af commit --repo {hf_repo} --revision {revision} --chute-id {chute_id}")

    def full_deploy_plan(
        self,
        adapter_source: str,
        deploy_repo: str,
        base_model: str = "Qwen/Qwen3-32B",
    ):
        """Print full deployment plan without executing.

        Use this to understand what will happen before committing resources.
        """
        print("=" * 60)
        print("DEPLOYMENT PLAN")
        print("=" * 60)
        print(f"\n1. MERGE LoRA adapter")
        print(f"   Base:    {base_model}")
        print(f"   Adapter: {adapter_source}")
        print(f"   Target:  {deploy_repo}")
        print(f"\n2. DEPLOY to Chutes (4×H200, SGLang)")
        print(f"   Image:   chutes/sglang:nightly-2025081600")
        print(f"   Concurrency: 40")
        print(f"\n3. COMMIT on chain (Subnet 120)")
        print(f"   Repo:    {deploy_repo}")
        print(f"\n4. WAIT for scoring (~48 hours)")
        print(f"   - Completeness >= 90% required")
        print(f"   - GAME z_score=1.0 (easier to beat)")
        print(f"   - Geometric mean across ALL environments")
        print(f"\nCOST ESTIMATE:")
        print(f"   Chutes inference: ~$X/hr for 4×H200")
        print(f"   Scoring period: ~48 hours minimum")
        print("=" * 60)
