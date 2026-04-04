"""High-level launcher for one-command training runs from a config file."""

from __future__ import annotations

import os
from pathlib import Path

from forge.config import ForgeConfig
from forge.core.control.service import CoreControlService
from forge.core.contracts.experiments import CreateExperimentRequest
from forge.core.contracts.tasks import TaskSubmission
from forge.core.contracts.templates import ExecutionOverrides
from forge.core.experiments.models import Experiment
from forge.core.experiments.models import TrainingLifecycleState
from forge.core.contracts.execution import ResourceRequest
from forge.foundation.schema import RequestContext
from forge.foundation.contracts import TrainingSpec
from forge.remote_ops.targon_rental_service import provision_targon_rental_ssh
from forge.training.config import SwiftConfig
from forge.tasks.training.launch_config import (
    HuggingFaceDatasetSource,
    LocalDatasetSource,
    ProvisionTargonSshRentalTarget,
    RegisteredMachineTarget,
    TrainingLaunchConfig,
    load_training_launch_config,
)


def _require_env_vars(keys: tuple[str, ...]) -> None:
    missing = [key for key in keys if not os.environ.get(key, "")]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")


def _count_jsonl_rows(dataset_path: str) -> int:
    total = 0
    with open(dataset_path, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                total += 1
    return total


def _resolve_dataset_path(source, forge_config: ForgeConfig) -> str:
    if isinstance(source, LocalDatasetSource):
        dataset_path = str(Path(source.path).expanduser().resolve())
        if not Path(dataset_path).exists():
            raise ValueError(f"Dataset file not found: {dataset_path}")
        return dataset_path
    if isinstance(source, HuggingFaceDatasetSource):
        try:
            from huggingface_hub import hf_hub_download
        except ImportError as exc:
            raise RuntimeError("huggingface_hub is required for hf_dataset_file launch configs") from exc
        return hf_hub_download(
            repo_id=source.repo_id,
            filename=source.filename,
            repo_type="dataset",
            revision=source.revision,
            token=forge_config.hf_token or None,
        )
    raise TypeError(f"Unsupported dataset source: {type(source)!r}")


def _derive_data_config(source, dataset_path: str) -> dict:
    count = getattr(source, "count", 0) or _count_jsonl_rows(dataset_path)
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


def _ensure_publish_destination(config: TrainingLaunchConfig, forge_config: ForgeConfig) -> None:
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
    api = HfApi(token=forge_config.hf_token or None)
    api.create_repo(repo_id=publish.hub_model_id, repo_type="model", private=publish.private, exist_ok=True)


def _resolve_target_name(config: TrainingLaunchConfig, forge_config: ForgeConfig) -> tuple[str, dict | None]:
    target = config.execution.target
    if target is None:
        return "", None
    if isinstance(target, RegisteredMachineTarget):
        return target.machine_name, None
    if isinstance(target, ProvisionTargonSshRentalTarget):
        payload = provision_targon_rental_ssh(
            forge_config,
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
    if config.publish.push_to_hub:
        # ms-swift routes hub operations through either HFHub or MSHub based on
        # `use_hf`. Local-file datasets still work with `use_hf=True`, so switch
        # back to the Hugging Face path when automatic upload is enabled.
        train_cfg.use_hf = True
        train_cfg.push_to_hub = True
        train_cfg.hub_model_id = config.publish.hub_model_id
    elif isinstance(config.dataset, LocalDatasetSource):
        # Keep the local-file smoke path on the explicit local dataset codepath.
        train_cfg.use_hf = False
    return train_cfg


def _upsert_launch_metadata(plane: CoreControlService, experiment: Experiment, launch_config: TrainingLaunchConfig, *, config_path: str) -> Experiment:
    experiment.results.extra["training_launch_config"] = launch_config.model_dump(mode="json")
    experiment.results.extra["training_launch_config_path"] = str(config_path)
    plane.save_experiment(
        experiment,
        context=RequestContext(actor="cli", source="cli.control.launch", reason="record training launch config"),
        action="record_training_launch_config",
    )
    return experiment


def _build_training_spec(experiment: Experiment, dataset_path: str) -> TrainingSpec:
    config = SwiftConfig.model_validate(experiment.train_config)
    environments = tuple(sorted(experiment.data_config.keys())) if experiment.data_config else tuple()
    return TrainingSpec(
        experiment_id=experiment.id,
        model=config.model,
        dataset_path=dataset_path,
        train_config=config,
        environments=environments,
        output_dir=config.output_dir,
    )


def launch_training_from_config(
    plane: CoreControlService,
    launch_config: TrainingLaunchConfig,
    *,
    forge_config: ForgeConfig | None = None,
    config_path: str = "",
) -> dict:
    forge_config = forge_config or ForgeConfig.load()
    _require_env_vars(launch_config.required_env)
    dataset_path = _resolve_dataset_path(launch_config.dataset, forge_config)
    _ensure_publish_destination(launch_config, forge_config)
    target_name, provision_payload = _resolve_target_name(launch_config, forge_config)
    train_cfg = _resolved_train_config(launch_config)

    if plane.load_experiment(launch_config.experiment.id) is not None:
        raise ValueError(f"Experiment already exists: {launch_config.experiment.id}")

    experiment = plane.create_experiment(
        CreateExperimentRequest(
            experiment_id=launch_config.experiment.id,
            variable=launch_config.experiment.variable,
            hypothesis=launch_config.experiment.hypothesis,
            status=launch_config.experiment.status,
            train_config=train_cfg.model_dump(mode="json"),
            data_config=_derive_data_config(launch_config.dataset, dataset_path),
            notes=launch_config.experiment.notes,
            context=RequestContext(actor="cli", source="cli.control.launch"),
        )
    )
    experiment = _upsert_launch_metadata(plane, experiment, launch_config, config_path=config_path)

    handle = plane.submit_task(
        TaskSubmission(
            experiment_id=launch_config.experiment.id,
            task_type="training",
            task_request=_build_training_spec(experiment, dataset_path).model_dump(mode="json"),
            template_id=launch_config.execution.template_id,
            bundle_dir=launch_config.execution.bundle_dir or None,
            overrides=ExecutionOverrides(
                image=launch_config.execution.image,
                target=target_name,
                detach=launch_config.execution.detach,
                resources=ResourceRequest.model_validate(launch_config.execution.resources.model_dump(mode="json")),
                runtime_env=launch_config.execution.runtime_env,
            ),
            context=RequestContext(actor="cli", source="cli.control.launch"),
        )
    )
    experiment = plane.load_experiment(launch_config.experiment.id)
    if experiment is not None:
        experiment.status = TrainingLifecycleState.RUNNING
        plane.save_experiment(experiment, context=RequestContext(actor="cli", source="cli.control.launch"), action="launch_training_set_running")
    return {
        "experiment_id": experiment.id,
        "dataset_path": dataset_path,
        "target": target_name,
        "template_id": launch_config.execution.template_id,
        "bundle_dir": launch_config.execution.bundle_dir,
        "run_handle": handle.model_dump(mode="json"),
        "provision": provision_payload,
    }


def launch_training_from_path(
    plane: CoreControlService,
    config_path: str,
    *,
    forge_config: ForgeConfig | None = None,
) -> dict:
    launch_config = load_training_launch_config(config_path)
    return launch_training_from_config(plane, launch_config, forge_config=forge_config, config_path=config_path)


__all__ = [
    "launch_training_from_config",
    "launch_training_from_path",
]
