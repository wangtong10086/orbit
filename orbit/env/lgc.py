"""LGC-v2 environment — logic/math puzzles.

Data validation (LgcEnv) and GEM interactive protocol (LgcGemEnv).
"""

from typing import Optional

from orbit.env.base import EnvProtocol, EnvSpec
from orbit.env.gem import GemEnv, Observation, StepResult


class LgcEnv(EnvProtocol):

    spec = EnvSpec(
        name="LGC-v2",
        version="1.0",
        task_count=250,
        completeness_threshold=0.9,
        scoring_weight=1.0,
        valid_roles={"user", "assistant"},
    )

    def clean_entry(self, record: dict) -> Optional[dict]:
        """LGC-v2: logic/math puzzles. Validate complete reasoning."""
        msgs = record.get("messages", [])
        if len(msgs) != 2:
            return None
        user_msg, asst_msg = msgs[0], msgs[1]
        if user_msg["role"] != "user" or asst_msg["role"] != "assistant":
            return None
        content = asst_msg["content"]
        if "<think>" in content and "</think>" not in content:
            return None
        if "```python" in user_msg["content"] and "```python" not in content:
            return None
        if "<think>" in content:
            after_think = content.split("</think>")[-1].strip()
            if len(after_think) < 1:
                return None
        if len(content.strip()) < 10:
            return None
        return record


class LgcGemEnv(GemEnv):
    """LGC-v2 GEM environment — single-turn logic puzzle solving."""

    spec = EnvSpec(
        name="LGC-v2",
        version="1.0",
        task_count=250,
        valid_roles={"user", "assistant"},
    )

    def reset(self, seed: int = 42) -> tuple[Observation, dict]:
        obs = Observation(
            text="Solve this logic puzzle.",
            metadata={"seed": seed},
        )
        return obs, {}

    def step(self, action: str) -> StepResult:
        # Single-turn: one answer terminates
        return StepResult(
            observation=Observation(text=""),
            reward=0.0,
            terminated=True,
        )

    def close(self) -> None:
        pass
