"""PRINT environment — predict program output.

Data validation (PrintEnv) and GEM interactive protocol (PrintGemEnv).
"""

from typing import Optional

from forge.env.base import EnvProtocol, EnvSpec
from forge.env.gem import GemEnv, Observation, StepResult
from forge.env.registry import EnvRegistry, EnvHub


@EnvRegistry.register("PRINT")
class PrintEnv(EnvProtocol):

    spec = EnvSpec(
        name="PRINT",
        version="1.0",
        task_count=200,
        completeness_threshold=0.9,
        scoring_weight=1.0,
        valid_roles={"user", "assistant"},
    )

    def clean_entry(self, record: dict) -> Optional[dict]:
        """PRINT: predict program output. Must have complete reasoning."""
        msgs = record.get("messages", [])
        if len(msgs) != 2:
            return None
        user_msg, asst_msg = msgs[0], msgs[1]
        if user_msg["role"] != "user" or asst_msg["role"] != "assistant":
            return None
        content = asst_msg["content"]
        if "<think>" in content and "</think>" not in content:
            return None
        after_think = content.split("</think>")[-1].strip() if "</think>" in content else content.strip()
        if len(after_think) < 1:
            return None
        return record


@EnvHub.register_gem("PRINT")
class PrintGemEnv(GemEnv):
    """PRINT GEM environment — single-turn program output prediction."""

    spec = EnvSpec(
        name="PRINT",
        version="1.0",
        task_count=200,
        valid_roles={"user", "assistant"},
    )

    def reset(self, seed: int = 42) -> tuple[Observation, dict]:
        obs = Observation(
            text="What does the following program output?",
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
