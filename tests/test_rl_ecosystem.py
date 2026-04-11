from __future__ import annotations

import json
from pathlib import Path

from affine_ms_swift.api import get_local_swift_fork, get_training_profile, resolve_training_profile
from affine_rl_runtime.api import (
    ArtifactDestinations,
    TrajectoryManifestV1,
    build_runtime_launch_manifest,
    read_runtime_launch_manifest,
    read_trajectory_manifest,
    write_runtime_launch_manifest,
    write_trajectory_manifest,
)
from orbit.integrations.rl_ecosystem import list_rl_training_profiles, resolve_rl_training_profile
from orbit.training.config import SwiftConfig


def test_affine_ms_swift_profile_registry_exposes_memorygym_profiles():
    profiles = {profile.profile_id for profile in list_rl_training_profiles()}
    assert "memorygym.ms_swift.grpo.server.v1" in profiles
    assert "memorygym.ms_swift.grpo.colocate.v1" in profiles
    assert "memorygym.ms_swift.ppo.colocate.v1" in profiles

    profile = get_training_profile("memorygym.ms_swift.grpo.server.v1")
    assert profile.env_pack_id == "memorygym"
    assert profile.topology == "server"

    colocate_profile = get_training_profile("memorygym.ms_swift.grpo.colocate.v1")
    assert colocate_profile.topology == "colocate"


def test_local_swift_fork_manifest_is_available():
    fork = get_local_swift_fork()
    assert fork is not None
    assert fork.upstream_project == "ms-swift"
    assert fork.fork_project == "affine-ms-swift-fork"
    assert fork.root.endswith("packages/affine_ms_swift/vendor/ms_swift_fork")
    assert fork.python_path_entry.endswith("packages/affine_ms_swift/vendor/ms_swift_fork")


def test_profile_resolution_rejects_unknown_override_keys():
    try:
        resolve_training_profile(
            "memorygym.ms_swift.grpo.server.v1",
            overrides={"unknown_key": 1},
        )
        assert False, "Expected unsupported override failure"
    except ValueError as exc:
        assert "unsupported keys" in str(exc)


def test_orbit_profile_resolution_injects_legacy_compatibility():
    train_cfg = SwiftConfig(
        model="Qwen/Qwen3-8B",
        train_type="rlhf",
        rlhf_type="grpo",
        profile_id="memorygym.ms_swift.grpo.server.v1",
        profile_overrides={"max_turns": 64},
        report_to="none",
        output_dir="/tmp/checkpoints",
    )

    resolved_train, rollout_server, rl_profile = resolve_rl_training_profile(train_cfg, None)

    assert resolved_train.external_plugins == ["scripts/memorygym_ms_swift_plugin.py"]
    assert resolved_train.swift_passthrough["use_gym_env"] is True
    assert resolved_train.swift_passthrough["gym_env"] == "memorygym_env"
    assert rollout_server is not None
    assert rollout_server.enabled is True
    assert rollout_server.max_turns == 64
    assert rollout_server.staged_python_packages == []
    assert rl_profile is not None
    assert rl_profile.env_pack_id == "memorygym"
    assert rl_profile.backend_kind == "ms_swift"


def test_colocate_profile_resolution_injects_colocate_defaults_without_rollout_server():
    train_cfg = SwiftConfig(
        model="Qwen/Qwen3-8B",
        train_type="rlhf",
        rlhf_type="grpo",
        profile_id="memorygym.ms_swift.grpo.colocate.v1",
        profile_overrides={"max_turns": 64, "vllm_max_model_len": 4096},
        report_to="none",
        output_dir="/tmp/checkpoints",
    )

    resolved_train, rollout_server, rl_profile = resolve_rl_training_profile(train_cfg, None)

    assert rollout_server is None
    assert resolved_train.external_plugins == ["scripts/memorygym_ms_swift_plugin.py"]
    assert resolved_train.swift_passthrough["vllm_mode"] == "colocate"
    assert resolved_train.swift_passthrough["use_gym_env"] is True
    assert resolved_train.swift_passthrough["gym_env"] == "memorygym_env"
    assert resolved_train.swift_passthrough["multi_turn_scheduler"] == "gym_scheduler"
    assert resolved_train.swift_passthrough["max_turns"] == 64
    assert resolved_train.swift_passthrough["vllm_max_model_len"] == 4096
    assert rl_profile is not None
    assert rl_profile.topology == "colocate"


def test_runtime_manifest_roundtrip(tmp_path):
    manifest = build_runtime_launch_manifest(
        profile_id="memorygym.ms_swift.grpo.server.v1",
        backend_kind="ms_swift",
        env_pack_id="memorygym",
        env_pack_version="0.1.0",
        episode_loop_version="memorygym.loop.v1",
        topology="server",
        policy_version="Qwen/Qwen3-8B",
        train_config_path="inputs/swift_config.yaml",
        dataset_path="inputs/train.jsonl",
        artifact_destinations=ArtifactDestinations(
            training_log="artifacts/training.log",
            rollout_log="artifacts/rollout.log",
            runtime_precheck_log="artifacts/runtime-precheck.log",
            checkpoints_dir="artifacts/checkpoints",
            trajectory_manifest="artifacts/trajectories/manifest.json",
        ),
        extra={"train_type": "rlhf", "rlhf_type": "grpo"},
    )
    target = tmp_path / "runtime_launch.json"
    write_runtime_launch_manifest(target, manifest)

    reloaded = read_runtime_launch_manifest(target)
    assert reloaded.profile_id == "memorygym.ms_swift.grpo.server.v1"
    assert reloaded.artifact_destinations.training_log == "artifacts/training.log"


def test_trajectory_manifest_roundtrip(tmp_path):
    manifest = TrajectoryManifestV1(
        env_pack_id="memorygym",
        env_pack_version="0.1.0",
        episode_loop_version="memorygym.loop.v1",
        policy_version="Qwen/Qwen3-8B",
        profile_id="memorygym.ms_swift.grpo.server.v1",
        topology="server",
        episodes=[
            {
                "episode_id": "ep-1",
                "seed": 11,
                "steps_path": "episodes/ep-1/steps.jsonl",
                "summary_path": "episodes/ep-1/summary.json",
            }
        ],
    )
    target = tmp_path / "trajectory_manifest.json"
    write_trajectory_manifest(target, manifest)

    reloaded = read_trajectory_manifest(target)
    assert reloaded.schema_version == "trajectory.v1"
    assert reloaded.episodes[0].episode_id == "ep-1"
