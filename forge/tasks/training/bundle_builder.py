"""Training bundle builder."""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

from forge.core.execution.bundle import JobBundle
from forge.core.contracts.execution import InputRef, JobKind, JobSpec, OutputRef, ResourceRequest
from forge.foundation.contracts import TrainingSpec
from forge.training.config import SwiftConfig
from forge.training.sft import SwiftBackend


def sanitize_job_id(raw: str, prefix: str = "job") -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", raw).strip("-_.")
    return slug or prefix


def _bundle_entrypoint_prelude() -> str:
    return """#!/usr/bin/env bash
set -euo pipefail
BUNDLE_ROOT="${BUNDLE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${BUNDLE_ROOT}/.." && pwd)}"
mkdir -p "${BUNDLE_ROOT}/artifacts" "${BUNDLE_ROOT}/runtime"
if [ -x "${PROJECT_ROOT}/.venv/bin/python" ]; then
    if [ -z "${FORGE_PYTHON:-}" ]; then
        export FORGE_PYTHON="${PROJECT_ROOT}/.venv/bin/python"
        export PATH="${PROJECT_ROOT}/.venv/bin:${PATH}"
    fi
else
    export FORGE_PYTHON="${FORGE_PYTHON:-python3}"
fi
if [ "${FORGE_SKIP_DOTENV:-0}" != "1" ] && [ -f "${PROJECT_ROOT}/.env" ]; then
    set -a
    . "${PROJECT_ROOT}/.env"
    set +a
fi
PARENT_ROOT="$(cd "${PROJECT_ROOT}/.." && pwd)"
if [ -d "${PARENT_ROOT}/affinetes" ]; then
    export PYTHONPATH="${PROJECT_ROOT}:${PARENT_ROOT}:${PYTHONPATH:-}"
else
    export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH:-}"
fi
cd "${PROJECT_ROOT}"
"""


def _hf_upload_epilogue(*, base_model: str, hub_model_id: str, tuner_type: str) -> str:
    # We bypass ms-swift's native push_to_hub path here because it writes
    # invalid HF metadata for cached local base-model paths. This post-training
    # wrapper stages the final artifacts, normalizes README/adapter metadata,
    # and then uploads through huggingface_hub under our own control.
    library_name = "peft" if tuner_type == "lora" else "transformers"
    tags = ["transformers", "affine-swarm"]
    if tuner_type == "lora":
        tags.insert(0, "lora")
    tags_block = "\n".join(f"- {tag}" for tag in tags)
    readme_body = (
        f"---\n"
        f"library_name: {library_name}\n"
        f"base_model: {base_model}\n"
        f"pipeline_tag: text-generation\n"
        f"tags:\n{tags_block}\n"
        f"---\n\n"
        f"# {hub_model_id.rsplit('/', 1)[-1]}\n\n"
        f"This model artifact was produced by Affine Swarm.\n\n"
        f"Base model: `{base_model}`\n"
    )
    return "\n".join(
        [
            'UPLOAD_ROOT="${PROJECT_ROOT}/artifacts/checkpoints"',
            'UPLOAD_DIR="$(ls -1dt "${UPLOAD_ROOT}"/*/ 2>/dev/null | head -n1 || true)"',
            'if [ -z "${UPLOAD_DIR}" ]; then',
            '    echo "No training output dir found under ${UPLOAD_ROOT}" >&2',
            "    exit 1",
            "fi",
            'UPLOAD_DIR="${UPLOAD_DIR%/}"',
            'export AFFINE_UPLOAD_DIR="${UPLOAD_DIR}"',
            'export AFFINE_UPLOAD_STAGING="${BUNDLE_ROOT}/runtime/hf_upload"',
            f"export AFFINE_BASE_MODEL={shlex.quote(base_model)}",
            f"export AFFINE_HUB_MODEL_ID={shlex.quote(hub_model_id)}",
            f"export AFFINE_MODEL_CARD={shlex.quote(readme_body)}",
            "\"${FORGE_PYTHON}\" - <<'PY'",
            "import json",
            "import os",
            "import shutil",
            "from pathlib import Path",
            "from transformers import AutoTokenizer",
            "",
            "run_dir = Path(os.environ['AFFINE_UPLOAD_DIR'])",
            "staging_dir = Path(os.environ['AFFINE_UPLOAD_STAGING'])",
            "base_model = os.environ['AFFINE_BASE_MODEL']",
            "model_card = os.environ['AFFINE_MODEL_CARD']",
            "hf_token = os.environ.get('HF_TOKEN', '').strip() or None",
            "if staging_dir.exists():",
            "    shutil.rmtree(staging_dir)",
            "staging_dir.mkdir(parents=True, exist_ok=True)",
            "for item in run_dir.iterdir():",
            "    if item.is_dir():",
            "        continue",
            "    shutil.copy2(item, staging_dir / item.name)",
            "checkpoint_dirs = sorted(path for path in run_dir.glob('checkpoint-*') if path.is_dir())",
            "if checkpoint_dirs:",
            "    checkpoint_dir = checkpoint_dirs[-1]",
            "    skip_names = {'README.md', 'optimizer.pt', 'scheduler.pt', 'rng_state.pth', 'trainer_state.json'}",
            "    for item in checkpoint_dir.iterdir():",
            "        if item.is_dir() or item.name in skip_names:",
            "            continue",
            "        shutil.copy2(item, staging_dir / item.name)",
            "(staging_dir / 'README.md').write_text(model_card, encoding='utf-8')",
            "adapter_config = staging_dir / 'adapter_config.json'",
            "if adapter_config.exists():",
            "    payload = json.loads(adapter_config.read_text(encoding='utf-8'))",
            "    payload['base_model_name_or_path'] = base_model",
            "    adapter_config.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\\n', encoding='utf-8')",
            "tokenizer_files = {'tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json'}",
            "if not any((staging_dir / name).exists() for name in tokenizer_files):",
            "    tokenizer = AutoTokenizer.from_pretrained(base_model, token=hf_token, trust_remote_code=True)",
            "    tokenizer.save_pretrained(staging_dir)",
            "PY",
            "\"${FORGE_PYTHON}\" - <<'PY'",
            "import os",
            "from huggingface_hub import HfApi",
            "",
            "token = os.environ.get('HF_TOKEN', '').strip()",
            "if not token:",
            "    raise SystemExit('HF_TOKEN is required for post-training Hugging Face upload')",
            "api = HfApi(token=token)",
            "api.upload_folder(",
            "    repo_id=os.environ['AFFINE_HUB_MODEL_ID'],",
            "    repo_type='model',",
            "    folder_path=os.environ['AFFINE_UPLOAD_STAGING'],",
            "    path_in_repo='',",
            "    commit_message='Upload training artifacts from Affine Swarm',",
            ")",
            "PY",
            "",
        ]
    )


class TrainBundleBuilder:
    def __init__(self, backend: SwiftBackend | None = None):
        self.backend = backend or SwiftBackend()

    def build(self, bundle_dir: str, *, spec: TrainingSpec, resources: ResourceRequest | None = None, overwrite: bool = False) -> JobBundle:
        issues = self.backend.validate_config(spec.train_config)
        if issues:
            raise ValueError(f"Invalid SwiftConfig: {issues}")
        bundle = JobBundle.create(bundle_dir, overwrite=overwrite)
        dataset_rel = bundle.copy_input(spec.dataset_path)
        cfg = SwiftConfig.model_validate(spec.train_config.model_dump())
        publish_to_hub = cfg.push_to_hub and bool(cfg.hub_model_id)
        cfg.output_dir = "artifacts/checkpoints"
        cfg.push_to_hub = False
        yaml_path = "inputs/swift_config.yaml"
        bundle.write_text(yaml_path, cfg.to_yaml("__AFFINE_DATASET_PATH__"))
        job = JobSpec(
            job_id=sanitize_job_id(spec.experiment_id, prefix="train"),
            kind=JobKind.TRAIN,
            resources=resources or ResourceRequest(),
            inputs=(InputRef(name="dataset", relative_path=dataset_rel), InputRef(name="swift_config", relative_path=yaml_path)),
            expected_outputs=(
                OutputRef(name="training_log", relative_path="artifacts/training.log"),
                OutputRef(name="checkpoints", relative_path="artifacts/checkpoints", kind="dir"),
            ),
            metadata={
                "task_type": "train",
                "model": cfg.model,
                "dataset_filename": Path(dataset_rel).name,
                "train_type": cfg.train_type,
            },
        )
        bundle.write_job(job)
        resolved_yaml_path = '"${BUNDLE_ROOT}/runtime/swift_config.resolved.yaml"'
        swift_cmd = cfg.swift_command_from_yaml(resolved_yaml_path)
        script_lines = [
            f'DATASET_PATH="${{BUNDLE_ROOT}}/{dataset_rel}"',
            'sed "s|__AFFINE_DATASET_PATH__|${DATASET_PATH}|g" "${BUNDLE_ROOT}/inputs/swift_config.yaml" > "${BUNDLE_ROOT}/runtime/swift_config.resolved.yaml"',
            'if [ -f /data/.affine/activate.sh ]; then source /data/.affine/activate.sh >/dev/null 2>&1; fi',
            f"{swift_cmd} 2>&1 | tee \"${{BUNDLE_ROOT}}/artifacts/training.log\"",
            "",
        ]
        if publish_to_hub:
            script_lines.append(_hf_upload_epilogue(base_model=spec.model, hub_model_id=cfg.hub_model_id, tuner_type=cfg.tuner_type))
        script = _bundle_entrypoint_prelude() + "\n".join(script_lines)
        bundle.write_text(job.entrypoint, script, executable=True)
        bundle.record_local_artifacts()
        return bundle


__all__ = ["TrainBundleBuilder", "sanitize_job_id"]
