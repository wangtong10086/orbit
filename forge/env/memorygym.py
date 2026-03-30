"""MEMORYGYM environment -- memory management data validation only."""

from typing import Optional

from forge.env.base import EnvProtocol, EnvSpec


class MemorygymEnv(EnvProtocol):
    """Data-only environment definition for MemoryGym synthesis outputs."""

    spec = EnvSpec(
        name="MEMORYGYM",
        version="1.0",
        task_count=200,
        completeness_threshold=0.8,
        scoring_weight=1.0,
        valid_roles={"system", "user", "assistant"},
        allowed_extra_fields=set(),
    )

    def clean_entry(self, record: dict) -> Optional[dict]:
        msgs = record.get("messages", [])
        if len(msgs) < 2:
            return None
        if not any(m.get("role") == "assistant" for m in msgs):
            return None
        record["env"] = self.spec.name
        return record
