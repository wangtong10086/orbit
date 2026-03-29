"""Build training datasets from canonical repository data."""

import os
from typing import Optional

HF_DATASET_REPO = "monokoco/affine-sft-data"
from forge.foundation.environment_catalog import default_environment_catalog
from forge.foundation.packing import Qwen3ConversationPacker
from forge.foundation.repository import LocalCanonicalRepository
from forge.pipeline.data import DatasetBuildPipeline


def build_from_canonical(
    output_path: str = "data/train_merged.jsonl",
    envs: Optional[list[str]] = None,
    min_score: float = 0.0,
    max_samples_per_env: int = 0,
    canonical_dir: str = "data/canonical",
) -> dict:
    """Build a merged training file from the local canonical repository."""

    repository = LocalCanonicalRepository(canonical_dir)
    pipeline = DatasetBuildPipeline(
        repository=repository,
        packer=Qwen3ConversationPacker(),
        catalog=default_environment_catalog(),
    )
    report = pipeline.build(
        output_path=output_path,
        envs=envs,
        min_score=min_score,
        max_per_env=max_samples_per_env,
    )
    return {
        "total": report.total,
        "by_env": report.by_env,
        "output_path": report.output_path,
    }


def upload_merged(
    local_path: str,
    token: str,
    remote_filename: str = "train_merged.jsonl",
    repo_id: str = HF_DATASET_REPO,
) -> str:
    """Upload merged training file to HF dataset repo.

    Returns:
        URL of uploaded file
    """
    from huggingface_hub import HfApi

    api = HfApi(token=token)
    api.upload_file(
        path_or_fileobj=local_path,
        path_in_repo=remote_filename,
        repo_id=repo_id,
        repo_type="dataset",
        commit_message=f"data: upload merged training data ({remote_filename})",
    )
    url = f"https://huggingface.co/datasets/{repo_id}/blob/main/{remote_filename}"
    print(f"Uploaded to {url}")
    return url
