"""Composable GAME trajectory-generator registry."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field

from orbit.foundation.schema import FrozenModel


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RANDOM_SCRIPT = PROJECT_ROOT / "scripts" / "game" / "generate_random.py"
POLICY_ROOT = PROJECT_ROOT / "artifacts" / "game_policies"


class GameTrajectoryGeneratorSpec(FrozenModel):
    name: str
    family: str
    script_path: str = ""
    env: dict[str, str] = Field(default_factory=dict)
    policy_path: str = ""
    policy_model_dir: str = ""
    supports_action_only: bool = True
    game_params: dict[str, object] = Field(default_factory=dict)
    default_iterations: int = 0


REGISTRY = {
    "othello": GameTrajectoryGeneratorSpec(
        name="othello_mcts",
        family="mcts",
        policy_model_dir=str(PROJECT_ROOT / "artifacts" / "game_policy_models" / "othello" / "default"),
        game_params={},
        default_iterations=0,
    ),
    "hex": GameTrajectoryGeneratorSpec(
        name="hex_mcts",
        family="mcts",
        policy_model_dir=str(PROJECT_ROOT / "artifacts" / "game_policy_models" / "hex" / "default"),
        game_params={"board_size": 7},
        default_iterations=0,
    ),
    "clobber": GameTrajectoryGeneratorSpec(
        name="clobber_mcts",
        family="mcts",
        policy_model_dir=str(PROJECT_ROOT / "artifacts" / "game_policy_models" / "clobber" / "default"),
        game_params={"rows": 5, "columns": 5},
        default_iterations=0,
    ),
    "liars_dice": GameTrajectoryGeneratorSpec(
        name="liars_dice_mccfr",
        family="mccfr",
        policy_path=str(POLICY_ROOT / "liars_dice" / "mccfr" / "policy.pkl"),
        policy_model_dir=str(PROJECT_ROOT / "artifacts" / "game_policy_models" / "liars_dice" / "default"),
        game_params={"numdice": 5},
        default_iterations=100,
    ),
    "leduc_poker": GameTrajectoryGeneratorSpec(
        name="leduc_poker_cfr",
        family="cfr",
        policy_path=str(POLICY_ROOT / "leduc_poker" / "cfr" / "policy.pkl"),
        policy_model_dir=str(PROJECT_ROOT / "artifacts" / "game_policy_models" / "leduc_poker" / "default"),
        game_params={},
        default_iterations=200,
    ),
    "goofspiel": GameTrajectoryGeneratorSpec(
        name="goofspiel_cfr",
        family="cfr",
        policy_path=str(POLICY_ROOT / "goofspiel" / "cfr" / "policy.pkl"),
        policy_model_dir=str(PROJECT_ROOT / "artifacts" / "game_policy_models" / "goofspiel" / "default"),
        game_params={"num_cards": 5, "imp_info": True, "points_order": "descending"},
        default_iterations=100,
    ),
    "gin_rummy": GameTrajectoryGeneratorSpec(
        name="gin_rummy_mccfr",
        family="mccfr",
        policy_path=str(POLICY_ROOT / "gin_rummy" / "mccfr" / "policy.pkl"),
        policy_model_dir=str(PROJECT_ROOT / "artifacts" / "game_policy_models" / "gin_rummy" / "default"),
        game_params={"hand_size": 7, "knock_card": 10},
        default_iterations=25,
    ),
}


def _env_key(game_name: str, param_name: str) -> str:
    safe_game = "".join(ch if ch.isalnum() else "_" for ch in game_name.upper())
    safe_param = "".join(ch if ch.isalnum() else "_" for ch in param_name.upper())
    return f"AFFINE_GAME_PARAM_{safe_game}_{safe_param}"


def _coerce_param(raw: str, current: object) -> object:
    if isinstance(current, bool):
        return raw.lower() in {"1", "true", "yes", "on"}
    if isinstance(current, int) and not isinstance(current, bool):
        return int(raw)
    if isinstance(current, float):
        return float(raw)
    return raw


def _resolve_game_params(game_name: str, params: dict[str, object]) -> dict[str, object]:
    resolved = dict(params)
    for key, current in list(resolved.items()):
        env_key = _env_key(game_name, key)
        raw = os.environ.get(env_key, "")
        if raw:
            resolved[key] = _coerce_param(raw, current)
    return resolved


def resolve_game_trajectory_generator(game_name: str) -> GameTrajectoryGeneratorSpec:
    """Return the active generator spec for a GAME environment."""

    try:
        spec = REGISTRY[game_name]
    except KeyError as exc:
        raise ValueError(f"Unsupported GAME environment: {game_name}") from exc
    return spec.model_copy(update={"game_params": _resolve_game_params(game_name, spec.game_params)})


def list_game_trajectory_generators() -> dict[str, GameTrajectoryGeneratorSpec]:
    return dict(REGISTRY)


def build_game_trajectory_generator(game_name: str, *, generator_source: str = "default"):
    spec = resolve_game_trajectory_generator(game_name)
    if generator_source == "policy_model":
        from orbit.data.game_generators.model_generators import PolicyModelTrajectoryGenerator

        return PolicyModelTrajectoryGenerator(
            name=f"{game_name}_policy_model",
            family="policy_model",
            game_params=spec.game_params,
            model_dir=spec.policy_model_dir,
        )
    if generator_source != "default":
        raise ValueError(f"Unsupported GAME generator source: {generator_source}")
    if spec.family in {"mcts", "minimax"}:
        from orbit.data.game_generators.search_generators import SearchTrajectoryGenerator

        return SearchTrajectoryGenerator(
            name=spec.name,
            family=spec.family,
            game_params=spec.game_params,
        )
    if spec.family in {"cfr", "mccfr", "deep_cfr"}:
        from orbit.data.game_generators.policy_generators import PolicySnapshotTrajectoryGenerator

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
