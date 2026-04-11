"""Public API for validated ms-swift launch profiles and the local fork."""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


class LegacyRolloutServerDefaults(BaseModel):
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8000
    max_turns: int = 128
    use_async_engine: bool = True
    vllm_gpu_memory_utilization: float = 0.35
    multi_turn_scheduler: str = ""
    vllm_max_model_len: int | None = None


class LegacyProfileCompatibility(BaseModel):
    external_plugins: list[str] = Field(default_factory=list)
    staged_python_packages: list[str] = Field(default_factory=list)
    swift_passthrough: dict[str, Any] = Field(default_factory=dict)
    swift_passthrough_overrides: dict[str, str] = Field(default_factory=dict)
    rollout_server: LegacyRolloutServerDefaults | None = None


class LaunchProfile(BaseModel):
    profile_id: str
    backend_kind: Literal["ms_swift"] = "ms_swift"
    runtime_kind: Literal["affine_rl_runtime"] = "affine_rl_runtime"
    env_pack_id: str
    optimizer_kind: str
    topology: Literal["server", "colocate"]
    trajectory_schema_version: Literal["trajectory.v1"] = "trajectory.v1"
    validation_state: Literal["validated", "experimental"] = "experimental"
    description: str = ""
    capability_tags: tuple[str, ...] = ()
    allowed_profile_overrides: tuple[str, ...] = ()
    legacy_compatibility: LegacyProfileCompatibility = Field(default_factory=LegacyProfileCompatibility)


class ResolvedLaunchProfile(BaseModel):
    profile: LaunchProfile
    external_plugins: list[str] = Field(default_factory=list)
    staged_python_packages: list[str] = Field(default_factory=list)
    swift_passthrough: dict[str, Any] = Field(default_factory=dict)
    rollout_server: LegacyRolloutServerDefaults | None = None


class LocalSwiftFork(BaseModel):
    root: str
    python_path_entry: str
    upstream_project: str = "ms-swift"
    upstream_version: str = ""
    fork_project: str = "affine-ms-swift-fork"
    fork_version: str = ""
    patch_source: str = "scripts/apply_ms_swift_patches.py"
    patched_files: list[str] = Field(default_factory=list)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _local_swift_fork_root() -> Path:
    explicit = os.environ.get("AFFINE_MS_SWIFT_FORK_ROOT", "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    return _repo_root() / "packages" / "affine_ms_swift" / "vendor" / "ms_swift_fork"


def get_local_swift_fork() -> LocalSwiftFork | None:
    root = _local_swift_fork_root()
    manifest_path = root / "FORK_MANIFEST.json"
    if not manifest_path.exists():
        return None
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["root"] = str(root)
    payload["python_path_entry"] = str(root)
    return LocalSwiftFork.model_validate(payload)


def _memorygym_grpo_server_profile() -> LaunchProfile:
    return LaunchProfile(
        profile_id="memorygym.ms_swift.grpo.server.v1",
        env_pack_id="memorygym",
        optimizer_kind="grpo",
        topology="server",
        validation_state="experimental",
        description="MemoryGym GRPO over native ms-swift gym env using a dedicated rollout server.",
        capability_tags=("gym_env", "grpo", "server_rollout"),
        allowed_profile_overrides=(
            "host",
            "port",
            "max_turns",
            "use_async_engine",
            "vllm_gpu_memory_utilization",
            "vllm_max_model_len",
        ),
        legacy_compatibility=LegacyProfileCompatibility(
            external_plugins=["scripts/memorygym_ms_swift_plugin.py"],
            swift_passthrough={
                "use_gym_env": True,
                "gym_env": "memorygym_env",
                "multi_turn_scheduler": "gym_scheduler",
            },
            rollout_server=LegacyRolloutServerDefaults(
                enabled=True,
                host="127.0.0.1",
                port=8000,
                max_turns=128,
                use_async_engine=True,
                vllm_gpu_memory_utilization=0.35,
                multi_turn_scheduler="gym_scheduler",
                vllm_max_model_len=4096,
            ),
        ),
    )


def _memorygym_grpo_colocate_profile() -> LaunchProfile:
    return LaunchProfile(
        profile_id="memorygym.ms_swift.grpo.colocate.v1",
        env_pack_id="memorygym",
        optimizer_kind="grpo",
        topology="colocate",
        validation_state="experimental",
        description="MemoryGym GRPO over the local affine ms-swift fork using colocate vLLM.",
        capability_tags=("gym_env", "grpo", "colocate"),
        allowed_profile_overrides=(
            "max_turns",
            "vllm_gpu_memory_utilization",
            "vllm_max_model_len",
            "completion_length_limit_scope",
        ),
        legacy_compatibility=LegacyProfileCompatibility(
            external_plugins=["scripts/memorygym_ms_swift_plugin.py"],
            swift_passthrough={
                "use_vllm": True,
                "vllm_mode": "colocate",
                "use_gym_env": True,
                "gym_env": "memorygym_env",
                "multi_turn_scheduler": "gym_scheduler",
                "async_generate": False,
                "vllm_gpu_memory_utilization": 0.35,
                "completion_length_limit_scope": "total",
            },
            swift_passthrough_overrides={
                "max_turns": "max_turns",
                "vllm_gpu_memory_utilization": "vllm_gpu_memory_utilization",
                "vllm_max_model_len": "vllm_max_model_len",
                "completion_length_limit_scope": "completion_length_limit_scope",
            },
        ),
    )


def _memorygym_ppo_colocate_profile() -> LaunchProfile:
    return LaunchProfile(
        profile_id="memorygym.ms_swift.ppo.colocate.v1",
        env_pack_id="memorygym",
        optimizer_kind="ppo",
        topology="colocate",
        validation_state="experimental",
        description="MemoryGym PPO over the local affine ms-swift fork using colocate vLLM.",
        capability_tags=("gym_env", "ppo", "colocate"),
        allowed_profile_overrides=(
            "max_turns",
            "vllm_gpu_memory_utilization",
            "vllm_max_model_len",
            "completion_length_limit_scope",
        ),
        legacy_compatibility=LegacyProfileCompatibility(
            external_plugins=["scripts/memorygym_ms_swift_plugin.py"],
            swift_passthrough={
                "use_vllm": True,
                "vllm_mode": "colocate",
                "use_gym_env": True,
                "gym_env": "memorygym_env",
                "multi_turn_scheduler": "gym_scheduler",
                "async_generate": False,
                "vllm_gpu_memory_utilization": 0.35,
                "completion_length_limit_scope": "total",
            },
            swift_passthrough_overrides={
                "max_turns": "max_turns",
                "vllm_gpu_memory_utilization": "vllm_gpu_memory_utilization",
                "vllm_max_model_len": "vllm_max_model_len",
                "completion_length_limit_scope": "completion_length_limit_scope",
            },
        ),
    )


_PROFILE_REGISTRY: dict[str, LaunchProfile] = {
    profile.profile_id: profile
    for profile in (
        _memorygym_grpo_server_profile(),
        _memorygym_grpo_colocate_profile(),
        _memorygym_ppo_colocate_profile(),
    )
}


def list_training_profiles() -> tuple[LaunchProfile, ...]:
    return tuple(_PROFILE_REGISTRY[key] for key in sorted(_PROFILE_REGISTRY))


def get_training_profile(profile_id: str) -> LaunchProfile:
    try:
        return _PROFILE_REGISTRY[profile_id]
    except KeyError as exc:
        known = ", ".join(sorted(_PROFILE_REGISTRY))
        raise ValueError(f"Unsupported ms-swift launch profile: {profile_id}. Known profiles: {known}") from exc


def resolve_training_profile(profile_id: str, overrides: dict[str, Any] | None = None) -> ResolvedLaunchProfile:
    profile = get_training_profile(profile_id)
    override_values = dict(overrides or {})
    unknown = sorted(set(override_values) - set(profile.allowed_profile_overrides))
    if unknown:
        raise ValueError(
            f"profile_overrides for {profile_id} contain unsupported keys: {', '.join(unknown)}"
        )

    compatibility = deepcopy(profile.legacy_compatibility.model_dump(mode="python"))
    rollout = compatibility.get("rollout_server")
    passthrough = compatibility.get("swift_passthrough") or {}
    passthrough_override_keys = compatibility.get("swift_passthrough_overrides") or {}
    if rollout is not None:
        for key, value in override_values.items():
            if key in rollout:
                rollout[key] = value
    for key, passthrough_key in passthrough_override_keys.items():
        if key in override_values:
            passthrough[passthrough_key] = override_values[key]
    compatibility["swift_passthrough"] = passthrough

    return ResolvedLaunchProfile(
        profile=profile,
        external_plugins=list(compatibility["external_plugins"]),
        staged_python_packages=list(compatibility["staged_python_packages"]),
        swift_passthrough=dict(compatibility["swift_passthrough"]),
        rollout_server=(
            LegacyRolloutServerDefaults.model_validate(rollout)
            if rollout is not None
            else None
        ),
    )


__all__ = [
    "LegacyProfileCompatibility",
    "LegacyRolloutServerDefaults",
    "LaunchProfile",
    "LocalSwiftFork",
    "ResolvedLaunchProfile",
    "get_local_swift_fork",
    "get_training_profile",
    "list_training_profiles",
    "resolve_training_profile",
]
