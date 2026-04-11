"""Public API scaffold for the AffineTES environment pack."""

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
    supported_topologies: tuple[str, ...] = ("server",)


def get_env_pack_definition() -> EnvPackDefinition:
    return EnvPackDefinition(
        env_pack_id="affinetes",
        env_pack_version="0.1.0",
        episode_loop_version="affinetes.loop.v1",
        action_codec_version="affinetes.codec.v1",
        reward_semantics_version="affinetes.reward.v1",
        telemetry_fields=("environment", "task", "score"),
        default_env_config={},
    )


__all__ = ["EnvPackDefinition", "get_env_pack_definition"]
