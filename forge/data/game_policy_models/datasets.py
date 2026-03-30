"""Expert rollout dataset builders for GAME policy models."""

from __future__ import annotations

from pathlib import Path
import random

import numpy as np
from pydantic import Field

from forge.data.game_generators.base import game_seed_rng
from forge.data.game_generators.policy_generators import (
    LoadedPolicySnapshot,
    build_policy_snapshot,
    load_policy_snapshot,
)
from forge.data.game_policy_models.featurizers import extract_state_features, legal_action_mask
from forge.data.game_trajectory_generators import resolve_game_trajectory_generator
from forge.foundation.schema import FrozenModel


class ExpertDatasetReport(FrozenModel):
    game: str
    generator_name: str
    generator_family: str
    output: str
    policy_path: str
    trajectories: int = 0
    samples: int = 0
    attempts: int = 0
    input_dim: int = 0
    action_dim: int = 0
    params: dict[str, object] = Field(default_factory=dict)


def default_expert_dataset_path(game_name: str) -> str:
    root = Path(__file__).resolve().parents[3] / "artifacts" / "game_expert_datasets"
    return str(root / game_name / "expert_dataset.npz")


def _policy_action(policy, state) -> int:
    try:
        probabilities = policy.action_probabilities(state)
    except TypeError:
        probabilities = policy.action_probabilities(state, player_id=state.current_player())
    legal = state.legal_actions(state.current_player())
    filtered = {action: float(prob) for action, prob in probabilities.items() if action in legal}
    if not filtered:
        raise RuntimeError("Policy snapshot returned no legal actions")
    return max(filtered.items(), key=lambda item: item[1])[0]


def _rollout_rows(
    *,
    game_name: str,
    seed: int,
    snapshot: LoadedPolicySnapshot,
    policy,
) -> list[tuple[np.ndarray, np.ndarray, int]] | None:
    import pyspiel

    np.random.seed(seed % (2**31))
    random.seed(seed)

    base_game = pyspiel.load_game(game_name, snapshot.metadata.params)
    game = pyspiel.convert_to_turn_based(base_game) if snapshot.metadata.transformed_to_turn_based else base_game
    state = game.new_initial_state()
    bot_player = random.randint(0, game.num_players() - 1)
    rows: list[tuple[np.ndarray, np.ndarray, int]] = []

    move_count = 0
    while not state.is_terminal() and move_count < 500:
        if state.is_chance_node():
            outcomes = state.chance_outcomes()
            state.apply_action(random.choices([a for a, _ in outcomes], [p for _, p in outcomes])[0])
            continue

        if state.is_simultaneous_node():
            actions = []
            for player in range(game.num_players()):
                legal = state.legal_actions(player)
                action = _policy_action(policy, state) if player == bot_player else random.choice(legal)
                if player == bot_player:
                    rows.append(
                        (
                            extract_state_features(state, player),
                            legal_action_mask(game, state, player),
                            action,
                        )
                    )
                actions.append(action)
            state.apply_actions(actions)
        else:
            current_player = state.current_player()
            legal = state.legal_actions(current_player)
            if current_player == bot_player:
                action = _policy_action(policy, state)
                rows.append(
                    (
                        extract_state_features(state, current_player),
                        legal_action_mask(game, state, current_player),
                        action,
                    )
                )
                state.apply_action(action)
            else:
                state.apply_action(random.choice(legal))
        move_count += 1

    if not state.is_terminal() or not rows:
        return None

    returns = state.returns()
    score = max(0.0, min(1.0, (returns[bot_player] + 1) / 2.0))
    if score < 0.5:
        return None
    return rows


def build_expert_dataset(
    *,
    game_name: str,
    output_path: str = "",
    trajectory_target: int = 50,
    start_seed: int = 100000,
    attempt_multiplier: int = 4,
    build_policy_if_missing: bool = True,
    policy_iterations: int = 0,
) -> ExpertDatasetReport:
    spec = resolve_game_trajectory_generator(game_name)
    if spec.family not in {"cfr", "mccfr", "deep_cfr"}:
        raise ValueError(f"{game_name} does not use a policy-based exact teacher")

    policy_path = Path(spec.policy_path)
    if build_policy_if_missing and not policy_path.exists():
        build_policy_snapshot(
            game_name=game_name,
            generator_name=spec.name,
            family=spec.family,
            params=spec.game_params,
            output_path=str(policy_path),
            iterations=policy_iterations or spec.default_iterations,
        )
    if not policy_path.exists():
        raise FileNotFoundError(
            f"Missing policy snapshot for {game_name}: {policy_path}. "
            f"Run `forge data game-build-policy --game {game_name}` first."
        )

    snapshot, policy = load_policy_snapshot(str(policy_path))
    seed_rng = game_seed_rng(game_name, start_seed)
    max_attempts = max(trajectory_target * max(attempt_multiplier, 1), trajectory_target)

    rows: list[tuple[np.ndarray, np.ndarray, int, int, int]] = []
    trajectories = 0
    attempts = 0

    while trajectories < trajectory_target and attempts < max_attempts:
        seed = seed_rng.randint(0, max(1, 2**31 - 2))
        rollout = _rollout_rows(
            game_name=game_name,
            seed=seed,
            snapshot=snapshot,
            policy=policy,
        )
        attempts += 1
        if not rollout:
            continue
        for row_idx, (features, mask, action) in enumerate(rollout):
            rows.append((features, mask, action, seed, trajectories))
        trajectories += 1

    if not rows:
        raise RuntimeError(f"GAME expert dataset generation produced no kept rows for {game_name}")

    output = Path(output_path or default_expert_dataset_path(game_name))
    output.parent.mkdir(parents=True, exist_ok=True)

    features = np.stack([row[0] for row in rows]).astype(np.float32)
    masks = np.stack([row[1] for row in rows]).astype(np.float32)
    actions = np.asarray([row[2] for row in rows], dtype=np.int64)
    seeds = np.asarray([row[3] for row in rows], dtype=np.int64)
    trajectory_ids = np.asarray([row[4] for row in rows], dtype=np.int64)
    np.savez_compressed(
        output,
        features=features,
        legal_masks=masks,
        actions=actions,
        seeds=seeds,
        trajectory_ids=trajectory_ids,
    )

    return ExpertDatasetReport(
        game=game_name,
        generator_name=spec.name,
        generator_family=spec.family,
        output=str(output),
        policy_path=str(policy_path),
        trajectories=trajectories,
        samples=int(actions.shape[0]),
        attempts=attempts,
        input_dim=int(features.shape[1]),
        action_dim=int(masks.shape[1]),
        params=snapshot.metadata.params,
    )
