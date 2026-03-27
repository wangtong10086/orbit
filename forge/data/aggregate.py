"""Aggregate canonical data from HF into ms-swift compatible format.

Downloads canonical JSONL files from HuggingFace, merges them into
a single JSONL file with only the `messages` field (ms-swift format),
and uploads the result back to HF for training.
"""

import json
import os
from typing import Optional


# Enabled environments and their canonical filenames on HF
ENABLED_ENVS = {
    "GAME": "canonical/game.jsonl",
    "NAVWORLD": "canonical/navworld.jsonl",
    "SWE-INFINITE": "canonical/swe_infinite.jsonl",
    "LIVEWEB": "canonical/liveweb.jsonl",
}

HF_DATASET_REPO = "monokoco/affine-sft-data"


def _clean_message(msg: dict) -> dict:
    """Clean a single message for ms-swift compatibility.

    Keeps: role, content, tool_calls, tool_call_id, tools
    Ensures content is never None (Qwen3 chat template breaks on None).
    """
    cleaned = {"role": msg["role"], "content": msg.get("content") or ""}
    # Preserve tool-related fields for agent training
    for key in ("tool_calls", "tool_call_id", "tools"):
        if key in msg:
            cleaned[key] = msg[key]
    return cleaned


def download_and_merge(
    token: str,
    output_path: str = "data/train_merged.jsonl",
    envs: Optional[list[str]] = None,
    min_score: float = 0.0,
    max_samples_per_env: int = 0,
) -> dict:
    """Download canonical files from HF and merge into ms-swift format.

    Args:
        token: HuggingFace API token
        output_path: Local path for the merged JSONL file
        envs: List of environment names to include (default: all enabled)
        min_score: Minimum score threshold (0 = no filter)
        max_samples_per_env: Max samples per env (0 = all)

    Returns:
        Dict with per-env counts and total
    """
    from huggingface_hub import hf_hub_download

    envs = envs or list(ENABLED_ENVS.keys())
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    stats = {}
    total = 0

    with open(output_path, "w") as out_f:
        for env in envs:
            if env not in ENABLED_ENVS:
                print(f"  Skipping unknown env: {env}")
                continue

            hf_path = ENABLED_ENVS[env]
            print(f"  Downloading {env} ({hf_path})...")

            try:
                local_file = hf_hub_download(
                    repo_id=HF_DATASET_REPO,
                    filename=hf_path,
                    repo_type="dataset",
                    token=token,
                )
            except Exception as e:
                print(f"  ERROR downloading {env}: {e}")
                stats[env] = {"count": 0, "error": str(e)}
                continue

            # Read and filter entries
            env_count = 0
            with open(local_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)

                    # Score filter
                    if min_score > 0 and entry.get("score", 0) < min_score:
                        continue

                    # Extract and clean messages
                    messages = entry.get("messages", [])
                    if len(messages) < 2:
                        continue

                    cleaned_msgs = [_clean_message(m) for m in messages]

                    # Write ms-swift format: just messages
                    out_f.write(json.dumps({"messages": cleaned_msgs}, ensure_ascii=False) + "\n")
                    env_count += 1

                    if max_samples_per_env and env_count >= max_samples_per_env:
                        break

            stats[env] = {"count": env_count}
            total += env_count
            print(f"  {env}: {env_count} samples")

    stats["total"] = total
    stats["output_path"] = output_path
    print(f"\nTotal: {total} samples -> {output_path}")
    return stats


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
