"""Model deployment pipeline: merge LoRA → HuggingFace → Chutes → chain commit.

Model merge logic delegated to forge.training.model.
"""

import os
import json
import tempfile
from pathlib import Path
from typing import Optional

from forge.config import ForgeConfig

# Re-export from training.model for backward compatibility
from forge.training.model import merge_lora_adapter, get_hf_latest_revision


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
