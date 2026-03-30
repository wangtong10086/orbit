"""Build training datasets from canonical repository data."""

import os
from typing import Optional

from forge.config import ForgeConfig
from forge.foundation.data_contracts import DatasetBuildReport, PublishReport
from forge.foundation.environment_catalog import default_environment_catalog
from forge.foundation.packing import Qwen3ConversationPacker
from forge.foundation.repository import LocalCanonicalRepository, canonical_fingerprint
from forge.pipeline.data import DatasetBuildPipeline


def dataset_repo_id(repo_id: str | None = None) -> str:
    """Resolve the target HF dataset repo with env override support."""

    return repo_id or os.environ.get("HF_DATASET_REPO", "") or ForgeConfig.load().hf_dataset_repo


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
    return DatasetBuildReport(
        total=report.total,
        by_env=report.by_env,
        output_path=report.output_path,
    ).model_dump(mode="json")


def upload_merged(
    local_path: str,
    token: str,
    remote_filename: str = "train_merged.jsonl",
    repo_id: str | None = None,
) -> str:
    """Upload merged training file to HF dataset repo.

    Returns:
        URL of uploaded file
    """
    from huggingface_hub import HfApi

    target_repo = dataset_repo_id(repo_id)
    api = HfApi(token=token)
    api.upload_file(
        path_or_fileobj=local_path,
        path_in_repo=remote_filename,
        repo_id=target_repo,
        repo_type="dataset",
        commit_message=f"data: upload merged training data ({remote_filename})",
    )
    url = f"https://huggingface.co/datasets/{target_repo}/blob/main/{remote_filename}"
    print(f"Uploaded to {url}")
    return url


def build_mixed_records(
    envs: Optional[list[str]] = None,
    min_score: float = 0.0,
    max_samples_per_env: int = 0,
    canonical_dir: str = "data/canonical",
) -> list[dict]:
    """Build viewer-friendly mixed records from canonical data."""

    repository = LocalCanonicalRepository(canonical_dir)
    catalog = default_environment_catalog()
    env_names = envs or catalog.list_data_envs()
    packer = Qwen3ConversationPacker()

    records: list[dict] = []
    for env_name in env_names:
        written = 0
        for record in repository.load(env_name):
            if record.get("score", 0.0) < min_score:
                continue
            packed = packer.pack(record)
            records.append(
                {
                    "messages": packed,
                    "env": env_name,
                    "score": float(record.get("score", 0.0)),
                    "source": str(record.get("source", "")),
                    "fingerprint": canonical_fingerprint(record),
                }
            )
            written += 1
            if max_samples_per_env and written >= max_samples_per_env:
                break
    return records


def build_mixed_dataset(
    envs: Optional[list[str]] = None,
    min_score: float = 0.0,
    max_samples_per_env: int = 0,
    canonical_dir: str = "data/canonical",
):
    """Build a Hugging Face Dataset object for the mixed train split."""

    try:
        from datasets import Dataset
    except ImportError as exc:
        raise RuntimeError("datasets is required to build mixed HF datasets") from exc

    records = build_mixed_records(
        envs=envs,
        min_score=min_score,
        max_samples_per_env=max_samples_per_env,
        canonical_dir=canonical_dir,
    )
    return Dataset.from_list(records)


def publish_mixed_dataset(
    token: str,
    repo_id: str | None = None,
    config_name: str = "mixed",
    split: str = "train",
    canonical_dir: str = "data/canonical",
    output_dir: str | None = None,
    envs: Optional[list[str]] = None,
    min_score: float = 0.0,
    max_samples_per_env: int = 0,
) -> PublishReport:
    """Publish the mixed training dataset to Hugging Face with viewer support."""

    dataset = build_mixed_dataset(
        envs=envs,
        min_score=min_score,
        max_samples_per_env=max_samples_per_env,
        canonical_dir=canonical_dir,
    )
    target_repo = dataset_repo_id(repo_id)

    parquet_path = None
    if output_dir:
        from pathlib import Path

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        parquet_path = out_dir / f"{config_name}-{split}.parquet"
        dataset.to_parquet(str(parquet_path))

    dataset.push_to_hub(
        target_repo,
        config_name=config_name,
        split=split,
        token=token,
    )
    return PublishReport(
        status="success",
        repo_id=target_repo,
        config=config_name,
        split=split,
        rows=len(dataset),
        parquet_path=str(parquet_path) if parquet_path else "",
    )
