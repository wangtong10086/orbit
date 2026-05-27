"""Training bundle builder."""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
import shutil
import subprocess

from orbit.core.execution.bundle import JobBundle
from orbit.core.contracts.execution import InputRef, JobKind, JobSpec, OutputRef, ResourceRequest
from orbit.foundation.contracts import TrainingSpec
from orbit.integrations.monorepo import ensure_monorepo_package_paths
from orbit.training.config import RolloutServerConfig, SwiftConfig, resolve_length_bucket_stages
from orbit.training.sft import SwiftBackend

ensure_monorepo_package_paths()


def sanitize_job_id(raw: str, prefix: str = "job") -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", raw).strip("-_.")
    return slug or prefix


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _get_local_swift_fork():
    from affine_ms_swift.api import get_local_swift_fork

    return get_local_swift_fork()


def _build_training_runtime_launch_manifest(*args, **kwargs):
    from orbit.integrations.rl_ecosystem import build_training_runtime_launch_manifest

    return build_training_runtime_launch_manifest(*args, **kwargs)


def _runtime_support_script(relative_path: str) -> str:
    return (_repo_root() / relative_path).read_text(encoding="utf-8")


def _try_git_revision(path: Path) -> str:
    git_dir = path if path.is_dir() else path.parent
    try:
        result = subprocess.run(
            ["git", "-C", str(git_dir), "rev-parse", "HEAD"],
            check=True,
            text=True,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return ""
    return result.stdout.strip()


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
MONOREPO_PYTHONPATH="${PROJECT_ROOT}/packages/rl_runtime/src:${PROJECT_ROOT}/packages/affine_ms_swift/src:${PROJECT_ROOT}/packages/env_memorygym/src:${PROJECT_ROOT}/packages/env_affinetes/src"
PARENT_ROOT="$(cd "${PROJECT_ROOT}/.." && pwd)"
if [ -d "${PARENT_ROOT}/affinetes" ]; then
    export PYTHONPATH="${PROJECT_ROOT}:${MONOREPO_PYTHONPATH}:${PARENT_ROOT}:${PYTHONPATH:-}"
else
    export PYTHONPATH="${PROJECT_ROOT}:${MONOREPO_PYTHONPATH}:${PYTHONPATH:-}"
fi
cd "${PROJECT_ROOT}"
"""


def _is_native_gkd(cfg: SwiftConfig) -> bool:
    return cfg.train_type == "rlhf" and cfg.rlhf_type == "gkd"


def _requires_vllm_runtime(cfg: SwiftConfig) -> bool:
    if not _is_native_gkd(cfg):
        return False
    return cfg.teacher_data_mode != "offline_topk"


def _swift_uses_vllm(cfg: SwiftConfig) -> bool:
    if cfg.train_type == "rlhf" and cfg.rlhf_type in {"grpo", "ppo"}:
        raw = cfg.swift_passthrough.get("use_vllm")
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.strip().lower() == "true"
    return False


def _wandb_script_setup_lines(cfg: SwiftConfig) -> list[str]:
    report_to = (cfg.report_to or "").strip().lower()
    if not report_to or report_to == "none" or "wandb" not in {part.strip() for part in report_to.split(",")}:
        return []
    return [
        'export WANDB_DIR="${WANDB_DIR:-${BUNDLE_ROOT}/artifacts/wandb}"',
        'mkdir -p "${WANDB_DIR}"',
        'export WANDB_MODE="${WANDB_MODE:-offline}"',
    ]


def _rollout_server_passthrough(cfg: SwiftConfig, rollout: RolloutServerConfig) -> dict[str, object]:
    values: dict[str, object] = {
        "use_vllm": True,
        "vllm_mode": "server",
        "vllm_server_host": rollout.host,
        "vllm_server_port": rollout.port,
        "vllm_server_pass_dataset": True,
        "async_generate": False,
        "vllm_use_async_engine": rollout.use_async_engine,
    }
    if cfg.tuner_type == "lora":
        values["vllm_enable_lora"] = True
        values["vllm_max_lora_rank"] = cfg.lora_rank
    return values


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
    tags = ["transformers", "personal-project"]
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
        f"This model artifact was produced by personal project ORBIT.\n\n"
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
            "    commit_message='Upload training artifacts from personal project ORBIT',",
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
        rollout_cfg = RolloutServerConfig.model_validate(spec.rollout_server.model_dump(mode="json")) if spec.rollout_server else None
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
        external_plugin_inputs = list(cfg.external_plugins)
        external_plugin_rels, external_plugin_values = _stage_local_paths(
            external_plugin_inputs,
            prefix="external-plugin",
            placeholder_prefix="__AFFINE_EXTERNAL_PLUGIN_PATH",
        )
        cfg.external_plugins = external_plugin_values
        rollout_runtime_plugin_paths = [
            f"${{BUNDLE_ROOT}}/{rel}" if rel else raw
            for rel, raw in zip(external_plugin_rels, external_plugin_inputs)
        ]
        staged_package_inputs = list(rollout_cfg.staged_python_packages) if rollout_cfg is not None else []
        staged_package_rels, _ = _stage_local_paths(
            staged_package_inputs,
            prefix="runtime-package",
            placeholder_prefix="__AFFINE_STAGED_PYTHON_PACKAGE_PATH",
        )
        staged_package_revisions = {
            Path(raw).name: _try_git_revision(Path(raw).expanduser()) for raw in staged_package_inputs if raw
        }
        if rollout_cfg is not None and rollout_cfg.enabled:
            rollout_passthrough = _rollout_server_passthrough(cfg, rollout_cfg)
            duplicate_rollout_keys = sorted(key for key in rollout_passthrough if key in cfg.swift_passthrough)
            if duplicate_rollout_keys:
                raise ValueError(
                    "rollout_server conflicts with swift_passthrough keys: " + ", ".join(duplicate_rollout_keys)
                )
            cfg.swift_passthrough = {**cfg.swift_passthrough, **rollout_passthrough}
        publish_to_hub = cfg.push_to_hub and bool(cfg.hub_model_id)
        cfg.output_dir = "artifacts/checkpoints"
        cfg.push_to_hub = False
        yaml_path = "inputs/swift_config.yaml"
        bundle.write_text(yaml_path, cfg.to_yaml("__AFFINE_DATASET_PATH__"))
        local_swift_fork = _get_local_swift_fork() if spec.stage_local_backend_fork else None
        local_swift_fork_rel = ""
        if local_swift_fork is not None:
            local_swift_fork_rel, _ = _stage_local_path(
                local_swift_fork.python_path_entry,
                prefix="runtime-swift-fork",
                placeholder="__AFFINE_LOCAL_SWIFT_FORK_PATH__",
            )

        if _is_native_gkd(cfg) and not local_swift_fork_rel:
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
        gpu_requested = bool((resources.gpu_count if resources is not None else 0) or cfg.num_gpus)
        if gpu_requested:
            bundle.write_text(
                "scripts/nvml_gpu_audit.py",
                _runtime_support_script("scripts/nvml_gpu_audit.py"),
                executable=True,
            )
        dataset_filename = Path(spec.dataset_remote_path).name if dataset_is_remote else Path(dataset_rel).name
        runtime_precheck_enabled = (
            bool(staged_package_rels)
            or bool(rollout_cfg and rollout_cfg.enabled)
            or bool(local_swift_fork_rel)
            or bool(spec.profile_id)
        )
        runtime_precheck_import_vllm = bool(rollout_cfg and rollout_cfg.enabled) or _requires_vllm_runtime(cfg) or _swift_uses_vllm(cfg)
        runtime_manifest_path = _build_training_runtime_launch_manifest(
            bundle=bundle,
            spec=spec,
            dataset_relative_path=(dataset_rel or spec.dataset_remote_path or dataset_filename),
            train_config_relative_path=yaml_path,
        )
        job = JobSpec(
            job_id=sanitize_job_id(spec.experiment_id, prefix="train"),
            kind=JobKind.TRAIN,
            resources=resources or ResourceRequest(),
            inputs=tuple(
                [
                    *([InputRef(name="dataset", relative_path=dataset_rel)] if dataset_rel else []),
                    InputRef(name="swift_config", relative_path=yaml_path),
                    *([InputRef(name="local_swift_fork", relative_path=local_swift_fork_rel)] if local_swift_fork_rel else []),
                    *([InputRef(name="model", relative_path=model_rel)] if model_rel else []),
                    *([InputRef(name="reference_model", relative_path=reference_model_rel)] if reference_model_rel and reference_model_rel != model_rel else []),
                    *([InputRef(name="teacher_model", relative_path=teacher_model_rel)] if teacher_model_rel and teacher_model_rel not in {model_rel, reference_model_rel} else []),
                    *(InputRef(name=f"adapter_{idx}", relative_path=rel) for idx, rel in enumerate(adapter_rels) if rel),
                    *(InputRef(name=f"ref_adapter_{idx}", relative_path=rel) for idx, rel in enumerate(ref_adapter_rels) if rel),
                    *(InputRef(name=f"teacher_adapter_{idx}", relative_path=rel) for idx, rel in enumerate(teacher_adapter_rels) if rel),
                    *(InputRef(name=f"external_plugin_{idx}", relative_path=rel) for idx, rel in enumerate(external_plugin_rels) if rel),
                    *(InputRef(name=f"runtime_package_{idx}", relative_path=rel) for idx, rel in enumerate(staged_package_rels) if rel),
                ]
            ),
            expected_outputs=(
                OutputRef(name="training_log", relative_path="artifacts/training.log"),
                *([OutputRef(name="nvml_audit", relative_path="artifacts/nvml-audit.jsonl")] if gpu_requested else []),
                *([OutputRef(name="nvml_audit_log", relative_path="artifacts/nvml-audit.log")] if gpu_requested else []),
                *( [OutputRef(name="rollout_log", relative_path="artifacts/rollout.log")] if rollout_cfg and rollout_cfg.enabled else [] ),
                *( [OutputRef(name="runtime_precheck_log", relative_path="artifacts/runtime-precheck.log")] if runtime_precheck_enabled else [] ),
                *( [OutputRef(name="rollout_model_download_log", relative_path="artifacts/rollout-model-download.log")] if rollout_cfg and rollout_cfg.enabled and not model_rel else [] ),
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
                        "profile_id": spec.profile_id,
                        "rl_backend_kind": spec.rl_profile.get("backend_kind", ""),
                        "rl_runtime_kind": spec.rl_profile.get("runtime_kind", ""),
                        "rl_env_pack_id": spec.rl_profile.get("env_pack_id", ""),
                        "rl_topology": spec.rl_profile.get("topology", ""),
                        "trajectory_schema_version": spec.rl_profile.get("trajectory_schema_version", ""),
                        "runtime_launch_manifest_path": runtime_manifest_path,
                    }
                    if spec.profile_id
                    else {}
                ),
                **(
                    {
                        "local_swift_fork_enabled": True,
                        "local_swift_fork_path": local_swift_fork_rel,
                        "local_swift_fork_version": local_swift_fork.fork_version,
                        "local_swift_upstream_version": local_swift_fork.upstream_version,
                    }
                    if local_swift_fork_rel and local_swift_fork is not None
                    else {}
                ),
                **(
                    {
                        "nvml_audit_enabled": True,
                        "nvml_audit_interval_seconds": 1.0,
                    }
                    if gpu_requested
                    else {}
                ),
                **(
                    {
                        "rollout_server_enabled": True,
                        "rollout_server_host": rollout_cfg.host,
                        "rollout_server_port": rollout_cfg.port,
                        "rollout_multi_turn_scheduler": rollout_cfg.multi_turn_scheduler,
                        "staged_python_package_revisions": staged_package_revisions,
                    }
                    if rollout_cfg and rollout_cfg.enabled
                    else {}
                ),
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
        external_plugin_replace_lines = []
        for idx, rel in enumerate(external_plugin_rels):
            if not rel:
                continue
            external_plugin_replace_lines.extend(
                [
                    f'EXTERNAL_PLUGIN_{idx}_PATH="${{BUNDLE_ROOT}}/{rel}"',
                    f'ESCAPED_EXTERNAL_PLUGIN_{idx}_PATH=$(printf \'%s\\n\' "${{EXTERNAL_PLUGIN_{idx}_PATH}}" | sed \'s/[&|]/\\\\&/g\')',
                    f'sed -i "s|__AFFINE_EXTERNAL_PLUGIN_PATH_{idx}__|${{ESCAPED_EXTERNAL_PLUGIN_{idx}_PATH}}|g" "${{BUNDLE_ROOT}}/runtime/swift_config.resolved.yaml"',
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
        rollout_setup_lines: list[str] = []
        if runtime_precheck_enabled:
            rollout_setup_lines.extend(
                [
                    'PRECHECK_LOG="${BUNDLE_ROOT}/artifacts/runtime-precheck.log"',
                    'echo "[ORBIT] checking ms-swift runtime..." | tee "${PRECHECK_LOG}"',
                    *(
                        [
                            'if ! "${ORBIT_PYTHON}" - <<\'PY\' >/dev/null 2>&1; then',
                            'import pynvml',
                            'PY',
                            '  echo "[ORBIT] installing nvidia-ml-py for NVML audit..." | tee -a "${PRECHECK_LOG}"',
                            '  "${ORBIT_PYTHON}" -m ensurepip --upgrade >/dev/null 2>&1 || true',
                            '  "${ORBIT_PYTHON}" -m pip install nvidia-ml-py 2>&1 | tee -a "${PRECHECK_LOG}"',
                            'fi',
                        ]
                        if gpu_requested
                        else []
                    ),
                    '"${ORBIT_PYTHON}" - <<\'PY\' 2>&1 | tee -a "${PRECHECK_LOG}"',
                    'import importlib.metadata as im',
                    'import json',
                    'import os',
                    'import pathlib',
                    'import swift',
                    "print(f'swift runtime import ok: version={getattr(swift, \"__version__\", \"unknown\")} path={pathlib.Path(swift.__file__).resolve()}')",
                    "try:",
                    "    print(f'affine-ms-swift-fork distribution version={im.version(\"affine-ms-swift-fork\")}')",
                    "except im.PackageNotFoundError:",
                    "    print('affine-ms-swift-fork distribution not installed')",
                    "fork_root = os.environ.get('AFFINE_MS_SWIFT_FORK_ROOT', '').strip()",
                    "if fork_root:",
                    "    manifest_path = pathlib.Path(fork_root) / 'FORK_MANIFEST.json'",
                    "    if manifest_path.exists():",
                    "        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))",
                    "        print(",
                    "            'affine-ms-swift-fork manifest: '",
                    "            + f\"upstream={manifest.get('upstream_version', '')} fork={manifest.get('fork_version', '')} patch_source={manifest.get('patch_source', '')}\"",
                    "        )",
                    *( ['import pynvml', "print('pynvml runtime import ok')"] if gpu_requested else [] ),
                    *(['import vllm', "print('vllm runtime import ok')"] if runtime_precheck_import_vllm else []),
                    *(
                        [
                            'import orbit_env_memorygym',
                            "print('orbit_env_memorygym runtime import ok')",
                            'import memorygym',
                            "print('memorygym runtime import ok')",
                        ]
                        if spec.rl_profile.get("env_pack_id") == "memorygym"
                        else []
                    ),
                    'PY',
                ]
            )
            for idx, rel in enumerate(staged_package_rels):
                rollout_setup_lines.extend(
                    [
                        f'RUNTIME_PACKAGE_{idx}_PATH="${{BUNDLE_ROOT}}/{rel}"',
                        f'echo "[ORBIT] installing staged python package ${{RUNTIME_PACKAGE_{idx}_PATH}}" | tee -a "${{PRECHECK_LOG}}"',
                        f'"${{ORBIT_PYTHON}}" -m ensurepip --upgrade >/dev/null 2>&1 || true',
                        f'"${{ORBIT_PYTHON}}" -m pip install -e "${{RUNTIME_PACKAGE_{idx}_PATH}}" 2>&1 | tee -a "${{PRECHECK_LOG}}"',
                    ]
                )
            if any("memorygym" in Path(path).name.lower() for path in staged_package_inputs):
                rollout_setup_lines.extend(
                    [
                    '"${ORBIT_PYTHON}" - <<\'PY\' 2>&1 | tee -a "${PRECHECK_LOG}"',
                    'import memorygym',
                    "print('memorygym runtime import ok')",
                    'PY',
                    ]
                )
        if rollout_cfg is not None and rollout_cfg.enabled:
            if not model_rel:
                rollout_setup_lines.extend(
                    [
                        'ROLLOUT_MODEL_DOWNLOAD_LOG="${BUNDLE_ROOT}/artifacts/rollout-model-download.log"',
                        'ROLLOUT_MODEL_PATH_FILE="${BUNDLE_ROOT}/runtime/rollout-model-path.txt"',
                        f'export AFFINE_ROLLOUT_MODEL_ID={shlex.quote(cfg.model)}',
                        'export AFFINE_ROLLOUT_MODEL_PATH_FILE="${ROLLOUT_MODEL_PATH_FILE}"',
                        'echo "[ORBIT] prefetching rollout model weights..." | tee -a "${PRECHECK_LOG}"',
                        'ROLLOUT_MODEL_RESOLVED_PATH=""',
                        '"${ORBIT_PYTHON}" - <<\'PY\' >"${ROLLOUT_MODEL_DOWNLOAD_LOG}" 2>&1 &',
                        'import os',
                        'from pathlib import Path',
                        'from huggingface_hub import snapshot_download',
                        '',
                        'target = snapshot_download(',
                        "    repo_id=os.environ['AFFINE_ROLLOUT_MODEL_ID'],",
                        "    token=os.environ.get('HF_TOKEN') or None,",
                        '    resume_download=True,',
                        ')',
                        "Path(os.environ['AFFINE_ROLLOUT_MODEL_PATH_FILE']).write_text(target, encoding='utf-8')",
                        "print(f'cached_model_path={target}')",
                        'PY',
                        'ROLLOUT_MODEL_DOWNLOAD_PID=$!',
                        'ROLLOUT_MODEL_DOWNLOAD_READY=0',
                        f'ROLLOUT_MODEL_DOWNLOAD_ATTEMPTS=$((({rollout_cfg.model_download_timeout_seconds} + {rollout_cfg.model_download_poll_seconds} - 1) / {rollout_cfg.model_download_poll_seconds}))',
                        'for _ in $(seq 1 "${ROLLOUT_MODEL_DOWNLOAD_ATTEMPTS}"); do',
                        '  if ! kill -0 "${ROLLOUT_MODEL_DOWNLOAD_PID}" 2>/dev/null; then',
                        '    wait "${ROLLOUT_MODEL_DOWNLOAD_PID}"',
                        '    ROLLOUT_MODEL_DOWNLOAD_READY=1',
                        '    break',
                        '  fi',
                        f'  sleep {rollout_cfg.model_download_poll_seconds}',
                        'done',
                        'if [ "${ROLLOUT_MODEL_DOWNLOAD_READY}" != "1" ]; then',
                        '  echo "[ORBIT] rollout model download did not finish in time" >&2',
                        '  kill "${ROLLOUT_MODEL_DOWNLOAD_PID}" >/dev/null 2>&1 || true',
                        '  wait "${ROLLOUT_MODEL_DOWNLOAD_PID}" >/dev/null 2>&1 || true',
                        '  exit 1',
                        'fi',
                        'if [ ! -f "${ROLLOUT_MODEL_PATH_FILE}" ]; then',
                        '  echo "[ORBIT] rollout model download did not produce a resolved path file" >&2',
                        '  exit 1',
                        'fi',
                        'ROLLOUT_MODEL_RESOLVED_PATH=$(cat "${ROLLOUT_MODEL_PATH_FILE}")',
                        'if [ -z "${ROLLOUT_MODEL_RESOLVED_PATH}" ]; then',
                        '  echo "[ORBIT] rollout model download returned an empty resolved path" >&2',
                        '  exit 1',
                        'fi',
                        'ROLLOUT_MODEL_PATH="${ROLLOUT_MODEL_RESOLVED_PATH}"',
                    ]
                )
            rollout_setup_lines.extend(
                [
                    'ROLLOUT_PID=""',
                    'cleanup_rollout_server() {',
                    '  if [ -n "${ROLLOUT_PID:-}" ] && kill -0 "${ROLLOUT_PID}" 2>/dev/null; then',
                    '    kill "${ROLLOUT_PID}" >/dev/null 2>&1 || true',
                    '    wait "${ROLLOUT_PID}" >/dev/null 2>&1 || true',
                    '  fi',
                    '}',
                    'trap cleanup_rollout_server EXIT',
                    'ROLLOUT_PLUGIN_ARGS=()',
                ]
            )
            for runtime_path in rollout_runtime_plugin_paths:
                quoted_runtime_path = f'"{runtime_path}"' if runtime_path.startswith("${") else shlex.quote(runtime_path)
                rollout_setup_lines.append(f"ROLLOUT_PLUGIN_ARGS+=(--external_plugins {quoted_runtime_path})")
            rollout_model_value = "${MODEL_PATH}" if model_rel else "${ROLLOUT_MODEL_PATH}"
            rollout_model_assignment = (
                f'"{rollout_model_value}"'
                if rollout_model_value.startswith("${")
                else shlex.quote(rollout_model_value)
            )
            rollout_setup_lines.extend(
                [
                    f"ROLLOUT_MODEL_PATH={rollout_model_assignment}",
                    'ROLLOUT_CMD=("${ORBIT_PYTHON}" -m swift.cli.main rollout --model "${ROLLOUT_MODEL_PATH}")',
                    *( [f'ROLLOUT_CMD+=(--model_type {shlex.quote(cfg.model_type)})'] if cfg.model_type else [] ),
                    f'ROLLOUT_CMD+=(--host {shlex.quote(rollout_cfg.host)} --port {rollout_cfg.port})',
                    f'ROLLOUT_CMD+=(--max_turns {rollout_cfg.max_turns})',
                    f'ROLLOUT_CMD+=(--multi_turn_scheduler {shlex.quote(rollout_cfg.multi_turn_scheduler)})',
                    f'ROLLOUT_CMD+=(--vllm_gpu_memory_utilization {rollout_cfg.vllm_gpu_memory_utilization})',
                    f'ROLLOUT_CMD+=(--vllm_use_async_engine {str(rollout_cfg.use_async_engine).lower()})',
                    *( [f'ROLLOUT_CMD+=(--vllm_max_model_len {rollout_cfg.vllm_max_model_len})'] if rollout_cfg.vllm_max_model_len else [] ),
                    *( ['ROLLOUT_CMD+=(--vllm_enable_lora true)', f'ROLLOUT_CMD+=(--vllm_max_lora_rank {cfg.lora_rank})'] if cfg.tuner_type == "lora" else [] ),
                    'ROLLOUT_CMD+=("${ROLLOUT_PLUGIN_ARGS[@]}")',
                    '"${ROLLOUT_CMD[@]}" >"${BUNDLE_ROOT}/artifacts/rollout.log" 2>&1 &',
                    'ROLLOUT_PID=$!',
                    'ROLLOUT_URL=' + shlex.quote(f"http://{rollout_cfg.host}:{rollout_cfg.port}{rollout_cfg.health_endpoint}"),
                    'ROLLOUT_READY=0',
                    f'ROLLOUT_ATTEMPTS=$((({rollout_cfg.startup_timeout_seconds} + {rollout_cfg.health_poll_seconds} - 1) / {rollout_cfg.health_poll_seconds}))',
                    'for _ in $(seq 1 "${ROLLOUT_ATTEMPTS}"); do',
                    '  if curl -fsS "${ROLLOUT_URL}" >/dev/null 2>&1; then',
                    '    ROLLOUT_READY=1',
                    '    break',
                    '  fi',
                    f'  sleep {rollout_cfg.health_poll_seconds}',
                    'done',
                    'if [ "${ROLLOUT_READY}" != "1" ]; then',
                    '  echo "[ORBIT] rollout server did not become healthy in time" >&2',
                    '  exit 1',
                    'fi',
                ]
            )
        swift_fork_setup_lines = []
        if local_swift_fork_rel:
            swift_fork_setup_lines.extend(
                [
                    f'AFFINE_SWIFT_FORK_PATH="${{BUNDLE_ROOT}}/{local_swift_fork_rel}"',
                    'export PYTHONPATH="${AFFINE_SWIFT_FORK_PATH}:${PYTHONPATH:-}"',
                    'echo "[ORBIT] using local ms-swift fork at ${AFFINE_SWIFT_FORK_PATH}"',
                ]
            )
        nvml_audit_setup_lines: list[str] = []
        if gpu_requested:
            nvml_audit_setup_lines.extend(
                [
                    'cleanup_nvml_audit() { :; }',
                    'NVML_AUDIT_PID=""',
                    'NVML_AUDIT_JSONL="${BUNDLE_ROOT}/artifacts/nvml-audit.jsonl"',
                    'NVML_AUDIT_LOG="${BUNDLE_ROOT}/artifacts/nvml-audit.log"',
                    'cleanup_nvml_audit() {',
                    '  if [ -n "${NVML_AUDIT_PID:-}" ] && kill -0 "${NVML_AUDIT_PID}" 2>/dev/null; then',
                    '    kill "${NVML_AUDIT_PID}" >/dev/null 2>&1 || true',
                    '    wait "${NVML_AUDIT_PID}" >/dev/null 2>&1 || true',
                    '  fi',
                    '}',
                    '"${ORBIT_PYTHON}" "${BUNDLE_ROOT}/scripts/nvml_gpu_audit.py" --output "${NVML_AUDIT_JSONL}" --interval-seconds 1.0 >"${NVML_AUDIT_LOG}" 2>&1 &',
                    'NVML_AUDIT_PID=$!',
                ]
            )

        script_lines = [
            *dataset_path_setup_lines,
            *swift_fork_setup_lines,
            'cleanup_rollout_server() { :; }',
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
            *external_plugin_replace_lines,
            'if [ -f /data/.affine/activate.sh ]; then source /data/.affine/activate.sh >/dev/null 2>&1; fi',
            'cd "${BUNDLE_ROOT}"',
            *_wandb_script_setup_lines(cfg),
            *(
                [
                    'echo "[ORBIT] applying ms-swift runtime patches..."',
                    '"${ORBIT_PYTHON}" "${BUNDLE_ROOT}/scripts/apply_ms_swift_patches.py"',
                ]
                if _is_native_gkd(cfg) and not local_swift_fork_rel
                else []
            ),
            *(
                _native_gkd_runtime_precheck_lines(require_vllm=_requires_vllm_runtime(cfg))
                if _is_native_gkd(cfg)
                else []
            ),
            *nvml_audit_setup_lines,
            *rollout_setup_lines,
            'cleanup_training_helpers() {',
            '  cleanup_nvml_audit',
            '  cleanup_rollout_server',
            '}',
            'trap cleanup_training_helpers EXIT',
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
