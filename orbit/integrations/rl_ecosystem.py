"""Composition root for RL runtime/backend/env-pack integrations."""

from __future__ import annotations

from typing import Iterable

from pydantic import Field

from orbit.core.execution.bundle import JobBundle
from orbit.foundation.schema import JsonValue, StrictModel
from orbit.foundation.contracts import TrainingSpec
from orbit.integrations.monorepo import ensure_monorepo_package_paths
from orbit.training.config import RolloutServerConfig, SwiftConfig

ensure_monorepo_package_paths()


class ResolvedRLTrainingProfile(StrictModel):
    profile_id: str
    backend_kind: str
    runtime_kind: str
    env_pack_id: str
    env_pack_version: str
    episode_loop_version: str
    optimizer_kind: str
    topology: str
    trajectory_schema_version: str
    validation_state: str
    description: str = ""
    capability_tags: tuple[str, ...] = ()


def _env_pack_registry() -> dict[str, object]:
    from orbit_env_affinetes.api import get_env_pack_definition as get_affinetes_env_pack
    from orbit_env_memorygym.api import get_env_pack_definition as get_memorygym_env_pack

    memorygym = get_memorygym_env_pack()
    affinetes = get_affinetes_env_pack()
    return {
        memorygym.env_pack_id: memorygym,
        affinetes.env_pack_id: affinetes,
    }


def list_rl_training_profiles():
    from affine_ms_swift.api import list_training_profiles

    return list_training_profiles()


def _merge_unique_paths(current: Iterable[str], additional: Iterable[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for raw in [*current, *additional]:
        value = str(raw)
        if not value or value in seen:
            continue
        seen.add(value)
        merged.append(value)
    return merged


def _merge_swift_passthrough(
    current: dict[str, JsonValue],
    profile_defaults: dict[str, object],
) -> dict[str, JsonValue]:
    conflicts = sorted(
        key for key, value in profile_defaults.items() if key in current and current[key] != value
    )
    if conflicts:
        raise ValueError(
            "training.profile_id conflicts with training.swift_passthrough keys: " + ", ".join(conflicts)
        )
    return {**profile_defaults, **current}


def resolve_rl_training_profile(
    train_cfg: SwiftConfig,
    rollout_server: RolloutServerConfig | None,
) -> tuple[SwiftConfig, RolloutServerConfig | None, ResolvedRLTrainingProfile | None]:
    if not train_cfg.profile_id:
        return train_cfg, rollout_server, None

    from affine_ms_swift.api import resolve_training_profile

    resolved = resolve_training_profile(train_cfg.profile_id, overrides=train_cfg.profile_overrides)
    env_pack = _env_pack_registry().get(resolved.profile.env_pack_id)
    if env_pack is None:
        raise ValueError(f"Unsupported env pack in profile {train_cfg.profile_id}: {resolved.profile.env_pack_id}")
    if resolved.profile.topology not in env_pack.supported_topologies:
        raise ValueError(
            f"Profile {train_cfg.profile_id} requires topology {resolved.profile.topology}, "
            f"but env pack {env_pack.env_pack_id} supports only {', '.join(env_pack.supported_topologies)}"
        )

    merged_train = train_cfg.model_copy(deep=True)
    merged_train.external_plugins = _merge_unique_paths(
        merged_train.external_plugins,
        resolved.external_plugins,
    )
    merged_train.swift_passthrough = _merge_swift_passthrough(
        merged_train.swift_passthrough,
        resolved.swift_passthrough,
    )

    merged_rollout = rollout_server.model_copy(deep=True) if rollout_server is not None else None
    if resolved.rollout_server is not None:
        defaults = resolved.rollout_server.model_dump(mode="json")
        if merged_rollout is None:
            merged_rollout = RolloutServerConfig.model_validate(defaults)
        else:
            merged_rollout = RolloutServerConfig.model_validate(
                {
                    **defaults,
                    **merged_rollout.model_dump(mode="json"),
                }
            )
        merged_rollout.staged_python_packages = _merge_unique_paths(
            merged_rollout.staged_python_packages,
            resolved.staged_python_packages,
        )

    metadata = ResolvedRLTrainingProfile(
        profile_id=resolved.profile.profile_id,
        backend_kind=resolved.profile.backend_kind,
        runtime_kind=resolved.profile.runtime_kind,
        env_pack_id=env_pack.env_pack_id,
        env_pack_version=env_pack.env_pack_version,
        episode_loop_version=env_pack.episode_loop_version,
        optimizer_kind=resolved.profile.optimizer_kind,
        topology=resolved.profile.topology,
        trajectory_schema_version=resolved.profile.trajectory_schema_version,
        validation_state=resolved.profile.validation_state,
        description=resolved.profile.description,
        capability_tags=resolved.profile.capability_tags,
    )
    return merged_train, merged_rollout, metadata


def build_training_runtime_launch_manifest(
    *,
    bundle: JobBundle,
    spec: TrainingSpec,
    dataset_relative_path: str,
    train_config_relative_path: str,
) -> str:
    if not spec.profile_id or not spec.rl_profile:
        return ""

    from affine_rl_runtime.api import ArtifactDestinations
    from affine_rl_runtime.api import build_runtime_launch_manifest
    from affine_rl_runtime.api import write_runtime_launch_manifest

    manifest = build_runtime_launch_manifest(
        profile_id=spec.profile_id,
        backend_kind=str(spec.rl_profile["backend_kind"]),
        env_pack_id=str(spec.rl_profile["env_pack_id"]),
        env_pack_version=str(spec.rl_profile["env_pack_version"]),
        episode_loop_version=str(spec.rl_profile["episode_loop_version"]),
        topology=str(spec.rl_profile["topology"]),
        policy_version=str(spec.rl_profile.get("policy_version", spec.model)),
        train_config_path=train_config_relative_path,
        dataset_path=dataset_relative_path,
        artifact_destinations=ArtifactDestinations(
            training_log="artifacts/training.log",
            rollout_log="artifacts/rollout.log",
            runtime_precheck_log="artifacts/runtime-precheck.log",
            checkpoints_dir="artifacts/checkpoints",
            trajectory_manifest="artifacts/trajectories/manifest.json",
        ),
        extra={
            "train_type": spec.train_config.train_type,
            "rlhf_type": spec.train_config.rlhf_type if spec.train_config.train_type == "rlhf" else "",
            "output_dir": spec.output_dir,
        },
    )
    relative_path = "runtime/rl_runtime_manifest.json"
    write_runtime_launch_manifest(bundle.path / relative_path, manifest)
    return relative_path


__all__ = [
    "ResolvedRLTrainingProfile",
    "build_training_runtime_launch_manifest",
    "list_rl_training_profiles",
    "resolve_rl_training_profile",
]
