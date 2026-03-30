"""Composable GAME trajectory-generator registry."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from forge.foundation.schema import FrozenModel


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RANDOM_SCRIPT = PROJECT_ROOT / "scripts" / "game" / "generate_random.py"
POLICY_ROOT = PROJECT_ROOT / "artifacts" / "game_policies"


class GameTrajectoryGeneratorSpec(FrozenModel):
    name: str
    family: str
    script_path: str = ""
    env: dict[str, str] = Field(default_factory=dict)
    policy_path: str = ""
    supports_action_only: bool = True
    game_params: dict[str, object] = Field(default_factory=dict)
    default_iterations: int = 0


REGISTRY = {
    "othello": GameTrajectoryGeneratorSpec(
        name="othello_mcts",
        family="mcts",
        game_params={},
        default_iterations=0,
    ),
    "hex": GameTrajectoryGeneratorSpec(
        name="hex_mcts",
        family="mcts",
        game_params={"board_size": 7},
        default_iterations=0,
    ),
    "clobber": GameTrajectoryGeneratorSpec(
        name="clobber_mcts",
        family="mcts",
        game_params={"rows": 5, "columns": 5},
        default_iterations=0,
    ),
    "liars_dice": GameTrajectoryGeneratorSpec(
        name="liars_dice_mccfr",
        family="mccfr",
        policy_path=str(POLICY_ROOT / "liars_dice" / "mccfr" / "policy.pkl"),
        game_params={"numdice": 5},
        default_iterations=100,
    ),
    "leduc_poker": GameTrajectoryGeneratorSpec(
        name="leduc_poker_cfr",
        family="cfr",
        policy_path=str(POLICY_ROOT / "leduc_poker" / "cfr" / "policy.pkl"),
        game_params={},
        default_iterations=200,
    ),
    "goofspiel": GameTrajectoryGeneratorSpec(
        name="goofspiel_cfr",
        family="cfr",
        policy_path=str(POLICY_ROOT / "goofspiel" / "cfr" / "policy.pkl"),
        game_params={"num_cards": 5, "imp_info": True, "points_order": "descending"},
        default_iterations=100,
    ),
    "gin_rummy": GameTrajectoryGeneratorSpec(
        name="gin_rummy_mccfr",
        family="mccfr",
        policy_path=str(POLICY_ROOT / "gin_rummy" / "mccfr" / "policy.pkl"),
        game_params={"hand_size": 7, "knock_card": 10},
        default_iterations=25,
    ),
}


def resolve_game_trajectory_generator(game_name: str) -> GameTrajectoryGeneratorSpec:
    """Return the active generator spec for a GAME environment."""

    try:
        return REGISTRY[game_name]
    except KeyError as exc:
        raise ValueError(f"Unsupported GAME environment: {game_name}") from exc


def list_game_trajectory_generators() -> dict[str, GameTrajectoryGeneratorSpec]:
    return dict(REGISTRY)


def build_game_trajectory_generator(game_name: str):
    spec = resolve_game_trajectory_generator(game_name)
    if spec.family in {"mcts", "minimax"}:
        from forge.data.game_generators.search_generators import SearchTrajectoryGenerator

        return SearchTrajectoryGenerator(
            name=spec.name,
            family=spec.family,
            game_params=spec.game_params,
        )
    if spec.family in {"cfr", "mccfr", "deep_cfr"}:
        from forge.data.game_generators.policy_generators import PolicySnapshotTrajectoryGenerator

        return PolicySnapshotTrajectoryGenerator(
            name=spec.name,
            family=spec.family,
            policy_path=spec.policy_path,
        )
    if spec.script_path:
        raise NotImplementedError(
            f"Script-only GAME generator `{spec.name}` is no longer the primary path"
        )
    raise ValueError(f"Unsupported GAME generator family: {spec.family}")
