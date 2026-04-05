"""LIVEWEB environment — browser agent web navigation.

Data validation (LivewebEnv) and GEM interactive protocol (LivewebGemEnv).
"""

from typing import Optional

from orbit.env.base import EnvProtocol, EnvSpec
from orbit.env.gem import GemEnv, Observation, StepResult


class LivewebEnv(EnvProtocol):

    spec = EnvSpec(
        name="LIVEWEB",
        version="1.0",
        task_count=200,
        completeness_threshold=0.8,
        scoring_weight=1.0,
        valid_roles={"system", "user", "assistant", "tool"},
        allowed_extra_fields={"tool_calls", "tool_call_id", "tools"},
        terminal_roles={"assistant", "tool"},
    )

    def clean_entry(self, record: dict) -> Optional[dict]:
        """LIVEWEB: browser agent. Basic validation."""
        msgs = record.get("messages", [])
        if len(msgs) < 3:
            return None
        if not any(m["role"] == "assistant" for m in msgs):
            return None
        return record


class LivewebGemEnv(GemEnv):
    """LIVEWEB GEM environment — interactive browser agent sessions."""

    spec = EnvSpec(
        name="LIVEWEB",
        version="1.0",
        task_count=200,
        valid_roles={"system", "user", "assistant", "tool"},
        terminal_roles={"assistant", "tool"},
    )

    def __init__(self):
        self._done: bool = False

    def reset(self, seed: int = 42) -> tuple[Observation, dict]:
        self._done = False
        obs = Observation(
            text="Navigate to the target page and complete the task.",
            metadata={"seed": seed},
        )
        return obs, {}

    def step(self, action: str) -> StepResult:
        return StepResult(
            observation=Observation(text="Page content: placeholder"),
            reward=0.0,
            terminated=self._done,
        )

    def close(self) -> None:
        self._done = True

    @property
    def is_interactive(self) -> bool:
        return True
