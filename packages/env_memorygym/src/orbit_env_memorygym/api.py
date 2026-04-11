"""Public API for the MemoryGym environment pack."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EnvPackDefinition(BaseModel):
    env_pack_id: str
    env_pack_version: str
    episode_loop_version: str
    action_codec_version: str
    reward_semantics_version: str
    telemetry_fields: tuple[str, ...] = ()
    default_env_config: dict[str, Any] = Field(default_factory=dict)
    supported_topologies: tuple[str, ...] = ("server", "colocate")


def get_env_pack_definition() -> EnvPackDefinition:
    return EnvPackDefinition(
        env_pack_id="memorygym",
        env_pack_version="0.1.0",
        episode_loop_version="memorygym.loop.v1",
        action_codec_version="memorygym.tool_call.v1",
        reward_semantics_version="memorygym.verifiable_reward.v1",
        telemetry_fields=(
            "parsed_action",
            "template",
            "tier",
            "seed",
            "terminated",
            "episode_stats",
        ),
        default_env_config={
            "template_name": "company",
            "tier": "standard",
            "reward_mode": "binary",
            "backend_type": "chromadb",
        },
    )


def register_ms_swift_plugin() -> None:
    from .swift_plugin import register_ms_swift_plugin as _register

    _register()


__all__ = [
    "EnvPackDefinition",
    "get_env_pack_definition",
    "register_ms_swift_plugin",
]
