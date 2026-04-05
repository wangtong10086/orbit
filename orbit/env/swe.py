"""SWE-INFINITE environment — software engineering bug fixing.

Data validation (SweEnv) and GEM interactive protocol (SweGemEnv).
"""

from typing import Optional

from orbit.env.base import EnvProtocol, EnvSpec
from orbit.env.gem import GemEnv, Observation, StepResult


class SweEnv(EnvProtocol):

    spec = EnvSpec(
        name="SWE-INFINITE",
        version="1.0",
        task_count=100,
        completeness_threshold=0.8,
        scoring_weight=1.0,
        valid_roles={"system", "user", "assistant"},
    )

    def clean_entry(self, record: dict) -> Optional[dict]:
        """SWE-SYNTH: multi-turn code fix. Validate structure."""
        msgs = record.get("messages", [])
        if len(msgs) < 4:
            return None
        if msgs[0]["role"] != "system":
            return None
        has_substance = any(
            m["role"] == "assistant" and len(m["content"]) > 20
            for m in msgs
        )
        if not has_substance:
            return None
        while msgs and msgs[-1]["role"] != "assistant":
            msgs.pop()
        record["messages"] = msgs
        if len(msgs) < 4:
            return None
        return record


class SweGemEnv(GemEnv):
    """SWE-INFINITE GEM environment — interactive code fixing sessions."""

    spec = EnvSpec(
        name="SWE-INFINITE",
        version="1.0",
        task_count=100,
    )

    def __init__(self):
        self._done: bool = False

    def reset(self, seed: int = 42) -> tuple[Observation, dict]:
        self._done = False
        obs = Observation(
            text="Fix the failing test in the repository.",
            metadata={"seed": seed},
        )
        return obs, {}

    def step(self, action: str) -> StepResult:
        return StepResult(
            observation=Observation(text="Test result: placeholder"),
            reward=0.0,
            terminated=self._done,
        )

    def close(self) -> None:
        self._done = True

    @property
    def is_interactive(self) -> bool:
        return True
