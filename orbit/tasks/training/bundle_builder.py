"""Training bundle builder."""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
import shutil

from orbit.core.execution.bundle import JobBundle
from orbit.core.contracts.execution import InputRef, JobKind, JobSpec, OutputRef, ResourceRequest
from orbit.foundation.contracts import TrainingSpec
from orbit.training.config import SwiftConfig, resolve_length_bucket_stages
from orbit.training.sft import SwiftBackend


def sanitize_job_id(raw: str, prefix: str = "job") -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", raw).strip("-_.")
    return slug or prefix


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _runtime_support_script(relative_path: str) -> str:
    return (_repo_root() / relative_path).read_text(encoding="utf-8")


def _bundle_entrypoint_prelude() -> str:
    return """#!/usr/bin/env bash
set -euo pipefail
BUNDLE_ROOT="${BUNDLE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${BUNDLE_ROOT}/.." && pwd)}"
mkdir -p "${BUNDLE_ROOT}/artifacts" "${BUNDLE_ROOT}/runtime"
if [ -x "${PROJECT_ROOT}/.venv/bin/python" ]; then
    if [ -z "${ORBIT_PYTHON:-}" ]; then
        export ORBIT_PYTHON="${PROJECT_ROOT}/.venv/bin/python"
        export PATH="${PROJECT_ROOT}/.venv/bin:${PATH}"
    fi
else
    export ORBIT_PYTHON="${ORBIT_PYTHON:-python3}"
fi
if [ "${ORBIT_SKIP_DOTENV:-0}" != "1" ] && [ -f "${PROJECT_ROOT}/.env" ]; then
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


def _is_native_gkd(cfg: SwiftConfig) -> bool:
    return cfg.train_type == "rlhf" and cfg.rlhf_type == "gkd"


def _requires_vllm_runtime(cfg: SwiftConfig) -> bool:
    if not _is_native_gkd(cfg):
        return False
    return cfg.teacher_data_mode != "offline_topk"


def _native_gkd_runtime_precheck_lines(*, require_vllm: bool) -> list[str]:
    required = "('torch', 'transformers', 'swift', 'vllm')" if require_vllm else "('torch', 'transformers', 'swift')"
    return [
        'echo "[ORBIT] native GKD run: checking runtime packages..."',
        "\"${ORBIT_PYTHON}\" - <<'PY'",
        "from importlib.util import find_spec",
        "",
        f"required = {required}",
        "missing = [name for name in required if find_spec(name) is None]",
        "if missing:",
        "    raise SystemExit(",
        "        'native GKD runtime missing required packages: '",
        "        + ', '.join(missing)",
        "        + '. Rebuild the default execution image or rerun orbit/setup/bootstrap.sh.'",
        "    )",
        "print('native GKD runtime check passed')",
        "PY",
    ]


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
        f"This model artifact was produced by Affine Orbit.\n\n"
        f"Base model: `{base_model}`\n"
    )
    return "\n".join(
        [
            'export AFFINE_UPLOAD_ROOT="${BUNDLE_ROOT}/artifacts"',
            'export AFFINE_UPLOAD_STAGING="${BUNDLE_ROOT}/runtime/hf_upload"',
            f"export AFFINE_BASE_MODEL={shlex.quote(base_model)}",
            f"export AFFINE_HUB_MODEL_ID={shlex.quote(hub_model_id)}",
            f"export AFFINE_MODEL_CARD={shlex.quote(readme_body)}",
            "\"${ORBIT_PYTHON}\" - <<'PY'",
            "import json",
            "import os",
            "import shutil",
            "from pathlib import Path",
            "from transformers import AutoTokenizer",
            "",
            "artifact_root = Path(os.environ['AFFINE_UPLOAD_ROOT'])",
            "staging_dir = Path(os.environ['AFFINE_UPLOAD_STAGING'])",
            "base_model = os.environ['AFFINE_BASE_MODEL']",
            "model_card = os.environ['AFFINE_MODEL_CARD']",
            "hf_token = os.environ.get('HF_TOKEN', '').strip() or None",
            "run_dir = None",
            "latest_mtime = -1.0",
            "for root in sorted(path for path in artifact_root.glob('checkpoints*') if path.is_dir()):",
            "    for child in root.iterdir():",
            "        if not child.is_dir():",
            "            continue",
            "        mtime = child.stat().st_mtime",
            "        if mtime > latest_mtime:",
            "            latest_mtime = mtime",
            "            run_dir = child",
            "if run_dir is None:",
            "    raise SystemExit(f'No training output dir found under {artifact_root}')",
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
            "\"${ORBIT_PYTHON}\" - <<'PY'",
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
            "    commit_message='Upload training artifacts from Affine Orbit',",
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
        dataset_rel = ""
        dataset_is_remote = bool(spec.dataset_remote_repo and spec.dataset_remote_path)
        if not dataset_is_remote:
            dataset_rel = bundle.copy_input(spec.dataset_path)
        cfg = SwiftConfig.model_validate(spec.train_config.model_dump())
        copied_inputs: dict[str, str] = {}

        def _stage_local_path(raw: str, *, prefix: str, placeholder: str = "__AFFINE_LOCAL_MODEL_PATH__") -> tuple[str, str]:
            source = Path(str(raw)).expanduser()
            try:
                exists = source.exists()
            except PermissionError:
                return "", raw
            if not exists:
                return "", raw
            cached = copied_inputs.get(str(source.resolve()))
            if cached:
                return cached, placeholder
            target_name = f"{prefix}-{source.name}"
            target_path = bundle.inputs_dir / target_name
            if source.is_dir():
                shutil.copytree(source, target_path)
            else:
                shutil.copy2(source, target_path)
            rel = str(target_path.relative_to(bundle.path))
            copied_inputs[str(source.resolve())] = rel
            return rel, placeholder

        def _stage_local_paths(values: list[str], *, prefix: str, placeholder_prefix: str) -> tuple[list[str], list[str]]:
            rels: list[str] = []
            resolved_values: list[str] = []
            for idx, raw in enumerate(values):
                rel, resolved = _stage_local_path(
                    raw,
                    prefix=f"{prefix}-{idx}",
                    placeholder=f"{placeholder_prefix}_{idx}__",
                )
                rels.append(rel)
                resolved_values.append(resolved)
            return rels, resolved_values

        model_rel, model_value = _stage_local_path(cfg.model, prefix="model")
        cfg.model = model_value
        reference_model_rel, reference_model_value = (
            _stage_local_path(cfg.reference_model, prefix="reference-model", placeholder="__AFFINE_LOCAL_REFERENCE_MODEL_PATH__")
            if cfg.reference_model
            else ("", cfg.reference_model)
        )
        cfg.reference_model = reference_model_value
        teacher_model_rel, teacher_model_value = (
            _stage_local_path(cfg.teacher_model, prefix="teacher-model", placeholder="__AFFINE_LOCAL_TEACHER_MODEL_PATH__")
            if cfg.teacher_model
            else ("", cfg.teacher_model)
        )
        cfg.teacher_model = teacher_model_value
        adapter_rels, adapter_values = _stage_local_paths(cfg.adapters, prefix="adapter", placeholder_prefix="__AFFINE_LOCAL_ADAPTER_PATH")
        cfg.adapters = adapter_values
        ref_adapter_rels, ref_adapter_values = _stage_local_paths(cfg.ref_adapters, prefix="ref-adapter", placeholder_prefix="__AFFINE_LOCAL_REF_ADAPTER_PATH")
        cfg.ref_adapters = ref_adapter_values
        teacher_adapter_rels, teacher_adapter_values = _stage_local_paths(
            cfg.teacher_adapters,
            prefix="teacher-adapter",
            placeholder_prefix="__AFFINE_LOCAL_TEACHER_ADAPTER_PATH",
        )
        cfg.teacher_adapters = teacher_adapter_values
        publish_to_hub = cfg.push_to_hub and bool(cfg.hub_model_id)
        cfg.output_dir = "artifacts/checkpoints"
        cfg.push_to_hub = False
        yaml_path = "inputs/swift_config.yaml"
        bundle.write_text(yaml_path, cfg.to_yaml("__AFFINE_DATASET_PATH__"))
        if _is_native_gkd(cfg):
            bundle.write_text(
                "scripts/apply_ms_swift_patches.py",
                _runtime_support_script("scripts/apply_ms_swift_patches.py"),
                executable=True,
            )
        bucketing_plan = None
        if spec.bucketing is not None:
            resolved_stages = resolve_length_bucket_stages(spec.bucketing)
            bucketing_plan = {
                "tokenizer_model": spec.bucketing.tokenizer_model or spec.model,
                "workers": spec.bucketing.workers,
                "batch_size": spec.bucketing.batch_size,
                "output_dir": spec.bucketing.output_dir,
                "stages": [
                    {
                        "name": stage.name,
                        "bucket_min_length": stage.bucket_min_length,
                        "bucket_max_length": stage.bucket_max_length,
                        "max_length": stage.max_length,
                        "output_filename": f"{sanitize_job_id(stage.name, prefix='bucket')}.jsonl",
                        "train_overrides": stage.train_overrides,
                    }
                    for stage in resolved_stages
                ],
            }
            bundle.write_text(
                "inputs/length_bucket_plan.json",
                json.dumps(bucketing_plan, ensure_ascii=False, indent=2) + "\n",
            )
            bundle.write_text(
                "scripts/split_ms_swift_dataset_by_length.py",
                _runtime_support_script("scripts/split_ms_swift_dataset_by_length.py"),
                executable=True,
            )
            bundle.write_text(
                "scripts/run_bucketed_swift_training.py",
                _runtime_support_script("scripts/run_bucketed_swift_training.py"),
                executable=True,
            )
        dataset_filename = Path(spec.dataset_remote_path).name if dataset_is_remote else Path(dataset_rel).name
        job = JobSpec(
            job_id=sanitize_job_id(spec.experiment_id, prefix="train"),
            kind=JobKind.TRAIN,
            resources=resources or ResourceRequest(),
            inputs=tuple(
                [
                    *([InputRef(name="dataset", relative_path=dataset_rel)] if dataset_rel else []),
                    InputRef(name="swift_config", relative_path=yaml_path),
                    *([InputRef(name="model", relative_path=model_rel)] if model_rel else []),
                    *([InputRef(name="reference_model", relative_path=reference_model_rel)] if reference_model_rel and reference_model_rel != model_rel else []),
                    *([InputRef(name="teacher_model", relative_path=teacher_model_rel)] if teacher_model_rel and teacher_model_rel not in {model_rel, reference_model_rel} else []),
                    *(InputRef(name=f"adapter_{idx}", relative_path=rel) for idx, rel in enumerate(adapter_rels) if rel),
                    *(InputRef(name=f"ref_adapter_{idx}", relative_path=rel) for idx, rel in enumerate(ref_adapter_rels) if rel),
                    *(InputRef(name=f"teacher_adapter_{idx}", relative_path=rel) for idx, rel in enumerate(teacher_adapter_rels) if rel),
                ]
            ),
            expected_outputs=(
                OutputRef(name="training_log", relative_path="artifacts/training.log"),
                OutputRef(name="checkpoints", relative_path="artifacts/checkpoints", kind="dir"),
                *( [OutputRef(name="bucket_manifest", relative_path="artifacts/bucket_manifest.json")] if bucketing_plan else [] ),
            ),
            metadata={
                "task_type": "train",
                "model": cfg.model,
                "dataset_filename": dataset_filename,
                "train_type": cfg.train_type,
                **({"rlhf_type": cfg.rlhf_type} if cfg.train_type == "rlhf" else {}),
                **({"bucketed_training": True, "bucket_stage_count": len(bucketing_plan["stages"])} if bucketing_plan else {}),
                **({"requires_vllm_runtime": True} if _requires_vllm_runtime(cfg) else {}),
                **(
                    {
                        "dataset_transport": "hf_staging",
                        "dataset_hf_repo": spec.dataset_remote_repo,
                        "dataset_hf_path": spec.dataset_remote_path,
                        "dataset_hf_repo_type": spec.dataset_remote_repo_type,
                    }
                    if dataset_is_remote
                    else {}
                ),
            },
        )
        bundle.write_job(job)
        resolved_yaml_path = '"${BUNDLE_ROOT}/runtime/swift_config.resolved.yaml"'
        swift_cmd = cfg.swift_command_from_yaml(resolved_yaml_path)
        adapter_replace_lines = []
        for idx, rel in enumerate(adapter_rels):
            if not rel:
                continue
            adapter_replace_lines.extend(
                [
                    f'ADAPTER_{idx}_PATH="${{BUNDLE_ROOT}}/{rel}"',
                    f'ESCAPED_ADAPTER_{idx}_PATH=$(printf \'%s\\n\' "${{ADAPTER_{idx}_PATH}}" | sed \'s/[&|]/\\\\&/g\')',
                    f'sed -i "s|__AFFINE_LOCAL_ADAPTER_PATH_{idx}__|${{ESCAPED_ADAPTER_{idx}_PATH}}|g" "${{BUNDLE_ROOT}}/runtime/swift_config.resolved.yaml"',
                ]
            )
        ref_adapter_replace_lines = []
        for idx, rel in enumerate(ref_adapter_rels):
            if not rel:
                continue
            ref_adapter_replace_lines.extend(
                [
                    f'REF_ADAPTER_{idx}_PATH="${{BUNDLE_ROOT}}/{rel}"',
                    f'ESCAPED_REF_ADAPTER_{idx}_PATH=$(printf \'%s\\n\' "${{REF_ADAPTER_{idx}_PATH}}" | sed \'s/[&|]/\\\\&/g\')',
                    f'sed -i "s|__AFFINE_LOCAL_REF_ADAPTER_PATH_{idx}__|${{ESCAPED_REF_ADAPTER_{idx}_PATH}}|g" "${{BUNDLE_ROOT}}/runtime/swift_config.resolved.yaml"',
                ]
            )
        teacher_adapter_replace_lines = []
        for idx, rel in enumerate(teacher_adapter_rels):
            if not rel:
                continue
            teacher_adapter_replace_lines.extend(
                [
                    f'TEACHER_ADAPTER_{idx}_PATH="${{BUNDLE_ROOT}}/{rel}"',
                    f'ESCAPED_TEACHER_ADAPTER_{idx}_PATH=$(printf \'%s\\n\' "${{TEACHER_ADAPTER_{idx}_PATH}}" | sed \'s/[&|]/\\\\&/g\')',
                    f'sed -i "s|__AFFINE_LOCAL_TEACHER_ADAPTER_PATH_{idx}__|${{ESCAPED_TEACHER_ADAPTER_{idx}_PATH}}|g" "${{BUNDLE_ROOT}}/runtime/swift_config.resolved.yaml"',
                ]
            )
        dataset_path_setup_lines = (
            [f'DATASET_PATH="${{AFFINE_DATASET_PATH:-${{BUNDLE_ROOT}}/{dataset_rel}}}"']
            if dataset_rel
            else [
                'DATASET_PATH="${AFFINE_DATASET_PATH:-}"',
                'if [ -z "${DATASET_PATH}" ]; then echo "Dataset path not resolved before training launch" >&2; exit 1; fi',
            ]
        )
        script_lines = [
            *dataset_path_setup_lines,
            'sed "s|__AFFINE_DATASET_PATH__|${DATASET_PATH}|g" "${BUNDLE_ROOT}/inputs/swift_config.yaml" > "${BUNDLE_ROOT}/runtime/swift_config.resolved.yaml"',
            *([f'MODEL_PATH="${{BUNDLE_ROOT}}/{model_rel}"',
               'ESCAPED_MODEL_PATH=$(printf \'%s\\n\' "${MODEL_PATH}" | sed \'s/[&|]/\\\\&/g\')',
               'sed -i "0,/__AFFINE_LOCAL_MODEL_PATH__/s|__AFFINE_LOCAL_MODEL_PATH__|${ESCAPED_MODEL_PATH}|" "${BUNDLE_ROOT}/runtime/swift_config.resolved.yaml"'] if model_rel else []),
            *([f'REFERENCE_MODEL_PATH="${{BUNDLE_ROOT}}/{reference_model_rel}"',
               'ESCAPED_REFERENCE_MODEL_PATH=$(printf \'%s\\n\' "${REFERENCE_MODEL_PATH}" | sed \'s/[&|]/\\\\&/g\')',
               'sed -i "s|__AFFINE_LOCAL_REFERENCE_MODEL_PATH__|${ESCAPED_REFERENCE_MODEL_PATH}|g" "${BUNDLE_ROOT}/runtime/swift_config.resolved.yaml"'] if reference_model_rel else []),
            *([f'TEACHER_MODEL_PATH="${{BUNDLE_ROOT}}/{teacher_model_rel}"',
               'ESCAPED_TEACHER_MODEL_PATH=$(printf \'%s\\n\' "${TEACHER_MODEL_PATH}" | sed \'s/[&|]/\\\\&/g\')',
               'sed -i "s|__AFFINE_LOCAL_TEACHER_MODEL_PATH__|${ESCAPED_TEACHER_MODEL_PATH}|g" "${BUNDLE_ROOT}/runtime/swift_config.resolved.yaml"'] if teacher_model_rel else []),
            *adapter_replace_lines,
            *ref_adapter_replace_lines,
            *teacher_adapter_replace_lines,
            'if [ -f /data/.affine/activate.sh ]; then source /data/.affine/activate.sh >/dev/null 2>&1; fi',
            'cd "${BUNDLE_ROOT}"',
            *(
                [
                    'echo "[ORBIT] applying ms-swift runtime patches..."',
                    '"${ORBIT_PYTHON}" "${BUNDLE_ROOT}/scripts/apply_ms_swift_patches.py"',
                ]
                if _is_native_gkd(cfg)
                else []
            ),
            *(
                _native_gkd_runtime_precheck_lines(require_vllm=_requires_vllm_runtime(cfg))
                if _is_native_gkd(cfg)
                else []
            ),
            *(
                [
                    'BUCKET_PLAN_PATH="${BUNDLE_ROOT}/inputs/length_bucket_plan.json"',
                    f'BUCKET_OUTPUT_DIR="${{BUNDLE_ROOT}}/{spec.bucketing.output_dir}"',
                    'BUCKET_MANIFEST_PATH="${BUNDLE_ROOT}/artifacts/bucket_manifest.json"',
                    '"${ORBIT_PYTHON}" "${BUNDLE_ROOT}/scripts/split_ms_swift_dataset_by_length.py" '
                    '"${DATASET_PATH}" '
                    '--output-dir "${BUCKET_OUTPUT_DIR}" '
                    '--plan-json "${BUCKET_PLAN_PATH}" '
                    '--manifest "${BUCKET_MANIFEST_PATH}"',
                    'BUNDLE_WORKSPACE="$(cd "${BUNDLE_ROOT}/.." && pwd)"',
                    '"${ORBIT_PYTHON}" "${BUNDLE_ROOT}/scripts/run_bucketed_swift_training.py" '
                    '--workspace "${BUNDLE_WORKSPACE}" '
                    '--base-config "${BUNDLE_ROOT}/runtime/swift_config.resolved.yaml" '
                    '--plan-json "${BUCKET_PLAN_PATH}" '
                    '--manifest "${BUCKET_MANIFEST_PATH}" '
                    f'--train-type "{cfg.train_type}" '
                    f'--nproc-per-node "{cfg.num_gpus}" '
                    '2>&1 | tee "${BUNDLE_ROOT}/artifacts/training.log"',
                ]
                if bucketing_plan
                else [f"{swift_cmd} 2>&1 | tee \"${{BUNDLE_ROOT}}/artifacts/training.log\""]
            ),
            "",
        ]
        if publish_to_hub:
            script_lines.append(_hf_upload_epilogue(base_model=spec.model, hub_model_id=cfg.hub_model_id, tuner_type=cfg.tuner_type))
        script = _bundle_entrypoint_prelude() + "\n".join(script_lines)
        bundle.write_text(job.entrypoint, script, executable=True)
        bundle.record_local_artifacts()
        return bundle


__all__ = ["TrainBundleBuilder", "sanitize_job_id"]
