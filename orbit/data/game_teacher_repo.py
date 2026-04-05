"""Upload GAME exact-teacher snapshots to a private Hugging Face model repo."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from pydantic import Field

from orbit.config import OrbitConfig
from orbit.data.game_generators.policy_generators import load_policy_snapshot
from orbit.foundation.schema import FrozenModel


class TeacherRepoUploadReport(FrozenModel):
    status: str = "success"
    repo_id: str = ""
    game: str = ""
    family: str = ""
    private: bool = True
    uploaded_files: list[str] = Field(default_factory=list)
    readme_updated: bool = False
    reason: str = ""


def _resolve_repo(repo_id: str = "") -> str:
    return repo_id or os.environ.get("HF_GAME_TEACHER_REPO", "") or OrbitConfig.load().hf_game_teacher_repo


def _resolve_token(token: str = "") -> str:
    return token or os.environ.get("HF_TOKEN", "") or OrbitConfig.load().hf_token


def _teacher_repo_readme(repo_id: str) -> str:
    return f"""# GAME Teacher Snapshots

This is a private Hugging Face model repo for exact `GAME` teacher artifacts.

Stored artifacts:

- `teachers/<game>/<family>/policy.pkl`
- `teachers/<game>/<family>/metadata.json`

These files are not end-user language models. They are exact policy snapshots used as offline teachers for:

1. teacher rollout generation
2. expert dataset build
3. small policy-model distillation

## Upload

```bash
orbit data game-build-policy --game leduc_poker
orbit data game-upload-teacher --game leduc_poker --repo {repo_id}
```

## Download

```python
from huggingface_hub import hf_hub_download

policy_path = hf_hub_download(
    repo_id="{repo_id}",
    repo_type="model",
    filename="teachers/leduc_poker/cfr/policy.pkl",
    token="YOUR_HF_TOKEN",
)
```

## Local Use

After downloading, point the local registry or CLI to the snapshot path and continue with:

```bash
orbit data game-build-expert-dataset --game leduc_poker --samples 128
orbit data game-train-policy-model --game leduc_poker --dataset artifacts/game_expert_datasets/leduc_poker/expert_dataset.npz
```
"""


def upload_teacher_snapshot(
    *,
    game_name: str,
    family: str,
    policy_path: str,
    repo_id: str = "",
    token: str = "",
    private: bool = True,
    update_readme: bool = True,
) -> TeacherRepoUploadReport:
    try:
        from huggingface_hub import HfApi
    except ImportError as exc:
        raise RuntimeError("huggingface_hub is required for GAME teacher upload") from exc

    resolved_repo = _resolve_repo(repo_id)
    if not resolved_repo:
        return TeacherRepoUploadReport(
            status="error",
            game=game_name,
            family=family,
            reason="HF_GAME_TEACHER_REPO not set",
        )
    resolved_token = _resolve_token(token)
    if not resolved_token:
        return TeacherRepoUploadReport(
            status="error",
            repo_id=resolved_repo,
            game=game_name,
            family=family,
            reason="HF_TOKEN not set",
        )

    snapshot = Path(policy_path)
    if not snapshot.exists():
        return TeacherRepoUploadReport(
            status="error",
            repo_id=resolved_repo,
            game=game_name,
            family=family,
            reason=f"teacher snapshot missing: {snapshot}",
        )

    loaded, _ = load_policy_snapshot(str(snapshot))
    metadata = loaded.metadata.model_dump(mode="json")
    remote_prefix = f"teachers/{game_name}/{family}"
    api = HfApi(token=resolved_token)
    api.create_repo(
        repo_id=resolved_repo,
        repo_type="model",
        private=private,
        exist_ok=True,
    )

    uploaded = []
    api.upload_file(
        path_or_fileobj=str(snapshot),
        path_in_repo=f"{remote_prefix}/policy.pkl",
        repo_id=resolved_repo,
        repo_type="model",
        commit_message=f"game: upload {game_name} {family} teacher snapshot",
    )
    uploaded.append(f"{remote_prefix}/policy.pkl")

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
        json.dump(metadata, tmp, indent=2, ensure_ascii=False)
        metadata_path = tmp.name
    try:
        api.upload_file(
            path_or_fileobj=metadata_path,
            path_in_repo=f"{remote_prefix}/metadata.json",
            repo_id=resolved_repo,
            repo_type="model",
            commit_message=f"game: upload {game_name} metadata",
        )
        uploaded.append(f"{remote_prefix}/metadata.json")
    finally:
        Path(metadata_path).unlink(missing_ok=True)

    readme_updated = False
    if update_readme:
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as tmp:
            tmp.write(_teacher_repo_readme(resolved_repo))
            readme_path = tmp.name
        try:
            api.upload_file(
                path_or_fileobj=readme_path,
                path_in_repo="README.md",
                repo_id=resolved_repo,
                repo_type="model",
                commit_message="docs: update GAME teacher repo README",
            )
            uploaded.append("README.md")
            readme_updated = True
        finally:
            Path(readme_path).unlink(missing_ok=True)

    return TeacherRepoUploadReport(
        status="success",
        repo_id=resolved_repo,
        game=game_name,
        family=family,
        private=private,
        uploaded_files=uploaded,
        readme_updated=readme_updated,
    )
