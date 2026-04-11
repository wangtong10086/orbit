"""High-level launcher for one-command training runs from a config file."""

from __future__ import annotations

import os
from pathlib import Path
import re

from orbit.config import OrbitConfig, load_dotenv
from orbit.core.control.service import CoreControlService
from orbit.core.contracts.experiments import CreateExperimentRequest
from orbit.core.contracts.tasks import TaskSubmission
from orbit.core.contracts.templates import ExecutionOverrides
from orbit.core.experiments.models import Experiment
from orbit.core.experiments.models import TrainingLifecycleState
from orbit.core.contracts.execution import ResourceRequest
from orbit.foundation.schema import RequestContext
from orbit.foundation.contracts import TrainingSpec
from orbit.integrations.rl_ecosystem import ResolvedRLTrainingProfile, resolve_rl_training_profile
from orbit.remote_ops.targon_rental_service import provision_targon_rental_ssh
from orbit.training.config import RolloutServerConfig, SwiftConfig, merge_swift_config_overrides, resolve_length_bucket_stages
from orbit.tasks.training.launch_config import (
    HuggingFaceDatasetSource,
    LocalDatasetSource,
    ProvisionTargonSshRentalTarget,
    RegisteredMachineTarget,
    TrainingLaunchConfig,
    load_training_launch_config,
)

_REMOTE_DATASET_STAGE_MIN_BYTES = 64 * 1024 * 1024


def _require_env_vars(keys: tuple[str, ...]) -> None:
    missing = [key for key in keys if not os.environ.get(key, "")]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")


def _uses_wandb(report_to: str | None) -> bool:
    if not report_to:
        return False
    normalized = report_to.strip().lower()
    if normalized in {"none", "tensorboard"}:
        return False
    return "wandb" in {part.strip() for part in normalized.split(",")}


def _wandb_runtime_env(train_cfg: SwiftConfig, orbit_config: OrbitConfig | None = None) -> dict[str, str]:
    if not _uses_wandb(train_cfg.report_to):
        return {}
    env: dict[str, str] = {}
    if train_cfg.wandb_project:
        env["WANDB_PROJECT"] = train_cfg.wandb_project
    if train_cfg.wandb_run_name:
        env["WANDB_NAME"] = train_cfg.wandb_run_name
    env["WANDB_DIR"] = "artifacts/wandb"
    if orbit_config is not None:
        wandb_key = orbit_config.wandb_api_key or ""
    else:
        wandb_key = os.environ.get("WANDB_API_KEY", "")
    env["WANDB_MODE"] = "online" if wandb_key.strip() else "offline"
    # Multi-process training on some rentals can hang while wandb probes GPU and
    # machine metadata. Keep run logging enabled, but disable background system
    # stats collection by default.
    env["WANDB__DISABLE_STATS"] = "true"
    env["WANDB__DISABLE_META"] = "true"
    env["WANDB__DISABLE_MACHINE_INFO"] = "true"
    return env


def _count_jsonl_rows(dataset_path: str) -> int:
    total = 0
    with open(dataset_path, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                total += 1
    return total


def _resolve_dataset_path(source, orbit_config: OrbitConfig) -> str:
    if isinstance(source, LocalDatasetSource):
        dataset_path = str(Path(source.path).expanduser().resolve())
        if not Path(dataset_path).exists():
            raise ValueError(f"Dataset file not found: {dataset_path}")
        return dataset_path
    if isinstance(source, HuggingFaceDatasetSource):
        return source.filename
    raise TypeError(f"Unsupported dataset source: {type(source)!r}")


def _derive_data_config(source, dataset_path: str) -> dict:
    count = getattr(source, "count", 0)
    if not count and isinstance(source, LocalDatasetSource):
        count = _count_jsonl_rows(dataset_path)
    if isinstance(source, LocalDatasetSource):
        return {
            source.label: {
                "dataset_file": Path(dataset_path).name,
                "source": "local_file",
                "count": count,
            }
        }
    if isinstance(source, HuggingFaceDatasetSource):
        return {
            source.label: {
                "dataset_repo": source.repo_id,
                "dataset_file": source.filename,
                "revision": source.revision,
                "source": "hf_dataset_file",
                "count": count,
            }
        }
    raise TypeError(f"Unsupported dataset source: {type(source)!r}")


def _dataset_source_remote_reference(source) -> dict[str, str]:
    if isinstance(source, HuggingFaceDatasetSource):
        return {
            "repo_id": source.repo_id,
            "path_in_repo": source.filename,
            "repo_type": "dataset",
            "filename": Path(source.filename).name,
        }
    return {}


def _ensure_publish_destination(config: TrainingLaunchConfig, orbit_config: OrbitConfig) -> None:
    publish = config.publish
    if not publish.push_to_hub:
        return
    if not publish.hub_model_id:
        raise ValueError("publish.hub_model_id is required when publish.push_to_hub=true")
    if not publish.create_repo:
        return
    try:
        from huggingface_hub import HfApi
    except ImportError as exc:
        raise RuntimeError("huggingface_hub is required for push_to_hub launch configs") from exc
    api = HfApi(token=orbit_config.hf_token or None)
    api.create_repo(repo_id=publish.hub_model_id, repo_type="model", private=publish.private, exist_ok=True)


def _resolve_target_name(config: TrainingLaunchConfig, orbit_config: OrbitConfig) -> tuple[str, dict | None]:
    target = config.execution.target
    if target is None:
        return "", None
    if isinstance(target, RegisteredMachineTarget):
        return target.machine_name, None
    if isinstance(target, ProvisionTargonSshRentalTarget):
        payload = provision_targon_rental_ssh(
            orbit_config,
            name=target.workload_name,
            resource=target.resource,
            image=target.image,
            project_id=target.project_id,
            ssh_key_uid=target.ssh_key_uid,
            public_key=target.public_key,
            ssh_port=target.ssh_port,
            machine_name=target.machine_name,
            use_ssh_daemon=target.use_ssh_daemon,
            wait=target.wait,
            timeout_seconds=target.timeout_seconds,
            poll_seconds=target.poll_seconds,
        )
        return target.machine_name, payload
    raise TypeError(f"Unsupported execution target: {type(target)!r}")


def _resolved_train_config(config: TrainingLaunchConfig):
    train_cfg = config.training.model_copy(deep=True)
    if _uses_wandb(train_cfg.report_to) and not train_cfg.wandb_run_name:
        train_cfg.wandb_run_name = config.experiment.id
    if train_cfg.tuner_type == "full":
        train_cfg.quant_method = None
        train_cfg.quant_bits = None
    if config.publish.push_to_hub:
        # ms-swift routes hub operations through either HFHub or MSHub based on
        # `use_hf`. Local-file datasets still work with `use_hf=True`, so switch
        # back to the Hugging Face path when automatic upload is enabled.
        train_cfg.use_hf = True
        train_cfg.push_to_hub = True
        train_cfg.hub_model_id = config.publish.hub_model_id
    return train_cfg


def _resolve_local_support_path(raw: str, *, base_dir: Path) -> str:
    target = Path(raw).expanduser()
    if target.is_absolute():
        return str(target.resolve())
    config_relative = (base_dir / target).resolve()
    if config_relative.exists():
        return str(config_relative)
    cwd_relative = (Path.cwd() / target).resolve()
    return str(cwd_relative)


def _resolve_support_paths_for_launch(
    *,
    train_cfg: SwiftConfig,
    rollout_server: RolloutServerConfig | None,
    config_path: str,
) -> tuple[SwiftConfig, RolloutServerConfig | None]:
    base_dir = Path(config_path).expanduser().resolve().parent if config_path else Path.cwd()
    resolved_train = train_cfg.model_copy(deep=True)
    if resolved_train.external_plugins:
        resolved_train.external_plugins = [
            _resolve_local_support_path(path, base_dir=base_dir) for path in resolved_train.external_plugins
        ]
    resolved_rollout = rollout_server.model_copy(deep=True) if rollout_server is not None else None
    if resolved_rollout is not None and resolved_rollout.staged_python_packages:
        resolved_rollout.staged_python_packages = [
            _resolve_local_support_path(path, base_dir=base_dir) for path in resolved_rollout.staged_python_packages
        ]
    return resolved_train, resolved_rollout


def _declared_launch_config_payload(config: TrainingLaunchConfig) -> dict:
    return config.model_dump(mode="json", exclude_unset=True)


def _resolved_bucket_plan_payload(
    train_cfg: SwiftConfig,
    bucketing,
) -> list[dict]:
    if bucketing is None:
        return []
    resolved_stages = resolve_length_bucket_stages(bucketing)
    payload: list[dict] = []
    for stage in resolved_stages:
        stage_cfg = merge_swift_config_overrides(train_cfg, stage.train_overrides)
        payload.append(
            {
                "name": stage.name,
                "bucket_min_length": stage.bucket_min_length,
                "bucket_max_length": stage.bucket_max_length,
                "max_length": stage.max_length,
                "per_device_train_batch_size": stage_cfg.per_device_train_batch_size,
                "gradient_accumulation_steps": stage_cfg.gradient_accumulation_steps,
                "dataset_num_proc": stage_cfg.dataset_num_proc,
                "train_config": stage_cfg.to_effective_dict(),
            }
        )
    return payload


def _resolved_launch_config_payload(
    config: TrainingLaunchConfig,
    *,
    train_cfg: SwiftConfig,
    bucket_plan_resolved: list[dict],
    rollout_server: RolloutServerConfig | None,
    rl_profile: ResolvedRLTrainingProfile | None,
) -> dict:
    payload = config.model_dump(mode="json")
    payload["training"] = train_cfg.to_effective_dict()
    if rollout_server is not None:
        payload["rollout_server"] = rollout_server.model_dump(mode="json")
    if bucket_plan_resolved:
        payload["bucketing_resolved"] = bucket_plan_resolved
    if rl_profile is not None:
        payload["rl_profile_resolved"] = rl_profile.model_dump(mode="json")
    return payload


def _is_native_gkd(train_cfg: SwiftConfig) -> bool:
    return train_cfg.train_type == "rlhf" and train_cfg.rlhf_type == "gkd"


def _requires_vllm_runtime(train_cfg: SwiftConfig) -> bool:
    return _is_native_gkd(train_cfg) and train_cfg.teacher_data_mode != "offline_topk"


def _upsert_launch_metadata(
    plane: CoreControlService,
    experiment: Experiment,
    launch_config: TrainingLaunchConfig,
    *,
    train_cfg: SwiftConfig,
    bucket_plan_resolved: list[dict],
    rollout_server: RolloutServerConfig | None,
    rl_profile: ResolvedRLTrainingProfile | None,
    config_path: str,
) -> Experiment:
    experiment.results.extra.pop("training_launch_config", None)
    experiment.results.extra["training_launch_config_declared"] = _declared_launch_config_payload(launch_config)
    experiment.results.extra["training_launch_config_resolved"] = _resolved_launch_config_payload(
        launch_config,
        train_cfg=train_cfg,
        bucket_plan_resolved=bucket_plan_resolved,
        rollout_server=rollout_server,
        rl_profile=rl_profile,
    )
    experiment.results.extra["training_launch_config_path"] = str(config_path)
    if bucket_plan_resolved:
        experiment.results.extra["training_bucket_plan_resolved"] = bucket_plan_resolved
    if _is_native_gkd(train_cfg):
        experiment.results.extra["training_launch_requires_vllm"] = _requires_vllm_runtime(train_cfg)
        experiment.results.extra["training_launch_runtime"] = "native_ms_swift_gkd"
    plane.save_experiment(
        experiment,
        context=RequestContext(actor="cli", source="cli.control.launch", reason="record training launch config"),
        action="record_training_launch_config",
    )
    return experiment


def _update_launch_phase(
    plane: CoreControlService,
    experiment: Experiment,
    *,
    phase: str,
    status: TrainingLifecycleState | None = None,
    error: str | None = None,
) -> Experiment:
    experiment.results.extra["training_launch_phase"] = phase
    if error:
        experiment.results.extra["training_launch_error"] = error
    if status is not None:
        experiment.status = status
    plane.save_experiment(
        experiment,
        context=RequestContext(actor="cli", source="cli.control.launch", reason=f"training launch phase: {phase}"),
        action="record_training_launch_phase",
    )
    return experiment


def _build_training_spec(experiment: Experiment, dataset_path: str) -> TrainingSpec:
    return _build_training_spec_with_dataset_staging(experiment, dataset_path, dataset_staging=None)


def _slug(raw: str, *, prefix: str = "dataset") -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", raw).strip("-_.")
    return slug or prefix


def _runtime_staging_repo(orbit_config: OrbitConfig) -> str:
    repo = orbit_config.hf_runtime_repo or orbit_config.hf_backup_repo
    if repo and orbit_config.hf_token:
        return repo
    return ""


def _should_stage_dataset_to_hf(launch_config: TrainingLaunchConfig, dataset_path: str, orbit_config: OrbitConfig) -> bool:
    if not isinstance(launch_config.dataset, LocalDatasetSource):
        return False
    if not launch_config.execution.template_id.startswith("targon-rental"):
        return False
    if not _runtime_staging_repo(orbit_config):
        return False
    dataset_file = Path(dataset_path)
    if not dataset_file.is_file():
        return False
    return dataset_file.stat().st_size >= _REMOTE_DATASET_STAGE_MIN_BYTES


def _upload_file_to_runtime_repo(*, local_path: str, repo_id: str, path_in_repo: str, token: str) -> None:
    from huggingface_hub import HfApi

    api = HfApi(token=token)
    api.upload_file(
        path_or_fileobj=local_path,
        path_in_repo=path_in_repo,
        repo_id=repo_id,
        repo_type="model",
        commit_message=f"runtime: upload {path_in_repo}",
    )


def _maybe_stage_dataset_to_hf(
    launch_config: TrainingLaunchConfig,
    dataset_path: str,
    *,
    orbit_config: OrbitConfig,
) -> dict[str, str]:
    if not _should_stage_dataset_to_hf(launch_config, dataset_path, orbit_config):
        return {}
    repo_id = _runtime_staging_repo(orbit_config)
    dataset_file = Path(dataset_path)
    path_in_repo = f"runtime-datasets/{_slug(launch_config.experiment.id, prefix='dataset')}/{dataset_file.name}"
    _upload_file_to_runtime_repo(
        local_path=str(dataset_file),
        repo_id=repo_id,
        path_in_repo=path_in_repo,
        token=orbit_config.hf_token,
    )
    return {
        "repo_id": repo_id,
        "path_in_repo": path_in_repo,
        "repo_type": "model",
        "filename": dataset_file.name,
    }


def _build_training_spec_with_dataset_staging(
    experiment: Experiment,
    dataset_path: str,
    *,
    train_config: SwiftConfig | None = None,
    dataset_staging: dict[str, str] | None,
    bucketing=None,
    bucketing_resolved: list[dict] | None = None,
    rollout_server: RolloutServerConfig | None = None,
    rl_profile: ResolvedRLTrainingProfile | None = None,
    stage_local_backend_fork: bool = False,
) -> TrainingSpec:
    config = train_config or SwiftConfig.model_validate(experiment.train_config)
    environments = tuple(sorted(experiment.data_config.keys())) if experiment.data_config else tuple()
    return TrainingSpec(
        experiment_id=experiment.id,
        model=config.model,
        dataset_path=dataset_path,
        dataset_remote_repo=(dataset_staging or {}).get("repo_id", ""),
        dataset_remote_path=(dataset_staging or {}).get("path_in_repo", ""),
        dataset_remote_repo_type=(dataset_staging or {}).get("repo_type", "model"),
        train_config=config,
        train_config_effective=config.to_effective_dict(),
        train_config_runtime=config.model_dump(mode="json"),
        bucketing=bucketing,
        bucketing_resolved=bucketing_resolved or [],
        rollout_server=rollout_server,
        stage_local_backend_fork=stage_local_backend_fork,
        profile_id=config.profile_id,
        rl_profile=rl_profile.model_dump(mode="json") if rl_profile is not None else {},
        environments=environments,
        output_dir=config.output_dir,
    )


def launch_training_from_config(
    plane: CoreControlService,
    launch_config: TrainingLaunchConfig,
    *,
    orbit_config: OrbitConfig | None = None,
    config_path: str = "",
) -> dict:
    load_dotenv()
    orbit_config = orbit_config or OrbitConfig.load()
    train_cfg = _resolved_train_config(launch_config)
    train_cfg, rollout_server, rl_profile = resolve_rl_training_profile(
        train_cfg,
        launch_config.rollout_server,
    )
    train_cfg, rollout_server = _resolve_support_paths_for_launch(
        train_cfg=train_cfg,
        rollout_server=rollout_server,
        config_path=config_path,
    )
    bucket_plan_resolved = _resolved_bucket_plan_payload(train_cfg, launch_config.bucketing)
    required_env = list(launch_config.required_env)
    _require_env_vars(tuple(dict.fromkeys(required_env)))
    dataset_path = _resolve_dataset_path(launch_config.dataset, orbit_config)
    dataset_staging = _dataset_source_remote_reference(launch_config.dataset) or _maybe_stage_dataset_to_hf(
        launch_config, dataset_path, orbit_config=orbit_config
    )
    _ensure_publish_destination(launch_config, orbit_config)

    if plane.load_experiment(launch_config.experiment.id) is not None:
        raise ValueError(f"Experiment already exists: {launch_config.experiment.id}")

    experiment = plane.create_experiment(
        CreateExperimentRequest(
            experiment_id=launch_config.experiment.id,
            variable=launch_config.experiment.variable,
            hypothesis=launch_config.experiment.hypothesis,
            status=launch_config.experiment.status,
            train_config=train_cfg.to_effective_dict(),
            data_config=_derive_data_config(launch_config.dataset, dataset_path),
            notes=launch_config.experiment.notes,
            context=RequestContext(actor="cli", source="cli.control.launch"),
        )
    )
    experiment = _upsert_launch_metadata(
        plane,
        experiment,
        launch_config,
        train_cfg=train_cfg,
        bucket_plan_resolved=bucket_plan_resolved,
        rollout_server=rollout_server,
        rl_profile=rl_profile,
        config_path=config_path,
    )
    experiment = _update_launch_phase(plane, experiment, phase="prepared", status=TrainingLifecycleState.PREPARED)

    try:
        if isinstance(launch_config.execution.target, ProvisionTargonSshRentalTarget):
            experiment = _update_launch_phase(
                plane,
                experiment,
                phase="provisioning_target",
                status=TrainingLifecycleState.PREPARED,
            )
        target_name, provision_payload = _resolve_target_name(launch_config, orbit_config)
    except Exception as exc:
        _update_launch_phase(
            plane,
            experiment,
            phase="provision_failed",
            status=TrainingLifecycleState.BLOCKED,
            error=str(exc),
        )
        raise

    experiment = _update_launch_phase(plane, experiment, phase="submitting", status=TrainingLifecycleState.PREPARED)

    training_spec = _build_training_spec_with_dataset_staging(
        experiment,
        dataset_path,
        train_config=train_cfg,
        dataset_staging=dataset_staging,
        bucketing=launch_config.bucketing,
        bucketing_resolved=bucket_plan_resolved,
        rollout_server=rollout_server,
        rl_profile=rl_profile,
        stage_local_backend_fork=launch_config.execution.stage_local_backend_fork,
    )

    handle = plane.submit_task(
        TaskSubmission(
            experiment_id=launch_config.experiment.id,
            task_type="training",
            task_request=training_spec.to_payload_dict(),
            template_id=launch_config.execution.template_id,
            bundle_dir=launch_config.execution.bundle_dir or None,
            overrides=ExecutionOverrides(
                image=launch_config.execution.image,
                target=target_name,
                detach=launch_config.execution.detach,
                resources=ResourceRequest.model_validate(launch_config.execution.resources.model_dump(mode="json")),
                runtime_env={**_wandb_runtime_env(train_cfg, orbit_config), **launch_config.execution.runtime_env},
            ),
            context=RequestContext(actor="cli", source="cli.control.launch"),
        )
    )
    experiment = plane.load_experiment(launch_config.experiment.id)
    if experiment is not None:
        experiment = _update_launch_phase(plane, experiment, phase="submitted", status=TrainingLifecycleState.RUNNING)
    return {
        "experiment_id": experiment.id,
        "dataset_path": dataset_path,
        "target": target_name,
        "template_id": launch_config.execution.template_id,
        "bundle_dir": launch_config.execution.bundle_dir,
        "run_handle": handle.model_dump(mode="json"),
        "provision": provision_payload,
        "dataset_staging": dataset_staging,
    }


def launch_training_from_path(
    plane: CoreControlService,
    config_path: str,
    *,
    orbit_config: OrbitConfig | None = None,
) -> dict:
    launch_config = load_training_launch_config(config_path)
    return launch_training_from_config(plane, launch_config, orbit_config=orbit_config, config_path=config_path)


__all__ = [
    "launch_training_from_config",
    "launch_training_from_path",
]
