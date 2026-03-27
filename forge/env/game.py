"""GAME environment — OpenSpiel strategy games.

Data validation (GameEnv) and GEM interactive protocol (GameGemEnv).
"""

from typing import Optional

from forge.env.base import EnvProtocol, EnvSpec
from forge.env.gem import GemEnv, Observation, StepResult
from forge.env.registry import EnvRegistry, EnvHub


@EnvRegistry.register("GAME")
class GameEnv(EnvProtocol):

    spec = EnvSpec(
        name="GAME",
        version="1.0",
        task_count=200,
        completeness_threshold=0.8,
        scoring_weight=3.0,
        valid_roles={"system", "user", "assistant"},
    )

    def clean_entry(self, record: dict) -> Optional[dict]:
        """GAME: multi-turn game playing. Validate complete conversations."""
        msgs = record.get("messages", [])
        if not msgs or msgs[0]["role"] != "system":
            return None
        roles_after_sys = [m["role"] for m in msgs[1:]]
        if "assistant" not in roles_after_sys or "user" not in roles_after_sys:
            return None
        if msgs[-1]["role"] != "assistant":
            return None
        record["messages"] = [m for m in msgs if m["content"].strip()]
        if len(record["messages"]) < 3:
            return None
        return record


@EnvHub.register_gem("GAME")
class GameGemEnv(GemEnv):
    """GAME GEM environment — interactive OpenSpiel game sessions."""

    spec = EnvSpec(
        name="GAME",
        version="1.0",
        task_count=200,
        scoring_weight=3.0,
    )

    def __init__(self):
        self._game_name: str = ""
        self._turn: int = 0
        self._done: bool = False

    def reset(self, seed: int = 42) -> tuple[Observation, dict]:
        self._turn = 0
        self._done = False
        self._game_name = "chess"  # Placeholder
        obs = Observation(
            text=f"Game: {self._game_name}. You play as Player 1. Make your move.",
            metadata={"game": self._game_name, "seed": seed},
        )
        return obs, {"game": self._game_name}

    def step(self, action: str) -> StepResult:
        self._turn += 1
        # Placeholder: actual game logic would come from OpenSpiel
        return StepResult(
            observation=Observation(
                text=f"Turn {self._turn}: Opponent responds. Your move.",
                metadata={"turn": self._turn},
            ),
            reward=0.0,
            terminated=self._done,
        )

    def close(self) -> None:
        self._done = True

    @property
    def is_interactive(self) -> bool:
        return True
