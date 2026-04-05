"""Offline-policy GAME trajectory generators for imperfect-information games."""

from __future__ import annotations

from datetime import datetime, timezone
import pickle
import random
from pathlib import Path

from pydantic import Field

from orbit.data.game_generators.base import (
    GameTrajectoryGeneratorReport,
    PolicyBuildReport,
    PolicyStatusEntry,
    append_jsonl_record,
    count_jsonl_records,
    ensure_game_scripts_path,
    game_seed_rng,
)
from orbit.foundation.schema import FrozenModel


class PolicySnapshotMetadata(FrozenModel):
    game: str
    algorithm: str
    family: str
    params: dict[str, object] = Field(default_factory=dict)
    iterations: int = 0
    transformed_to_turn_based: bool = False
    built_at: str = ""


class LoadedPolicySnapshot(FrozenModel):
    metadata: PolicySnapshotMetadata
    policy_path: str


def _default_iterations(game_name: str, family: str) -> int:
    if game_name == "leduc_poker":
        return 200
    if game_name == "liars_dice":
        return 100
    if game_name == "goofspiel":
        return 100
    if game_name == "gin_rummy":
        return 25
    return 50


def _build_solver(game_name: str, *, family: str, params: dict[str, object]):
    import pyspiel
    from open_spiel.python.algorithms import cfr, external_sampling_mccfr

    transformed = False
    if family == "cfr":
        game = pyspiel.load_game(game_name, params)
        if game_name == "goofspiel":
            game = pyspiel.convert_to_turn_based(game)
            transformed = True
        return game, transformed, cfr.CFRSolver(game)

    if family == "mccfr":
        game = pyspiel.load_game(game_name, params)
        solver = external_sampling_mccfr.ExternalSamplingSolver(
            game,
            average_type=external_sampling_mccfr.AverageType.FULL,
        )
        return game, transformed, solver

    raise ValueError(f"Unsupported policy family: {family}")


def _advance_solver(solver, family: str, iterations: int) -> None:
    if family == "cfr":
        for _ in range(iterations):
            solver.evaluate_and_update_policy()
        return
    if family == "mccfr":
        for _ in range(iterations):
            solver.iteration()
        return
    raise ValueError(f"Unsupported policy family: {family}")


def _average_policy(solver, family: str):
    if family in {"cfr", "mccfr"}:
        return solver.average_policy()
    raise ValueError(f"Unsupported policy family: {family}")


def build_policy_snapshot(
    *,
    game_name: str,
    generator_name: str,
    family: str,
    params: dict[str, object],
    output_path: str,
    iterations: int | None = None,
) -> PolicyBuildReport:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    resolved_iterations = iterations or _default_iterations(game_name, family)
    game, transformed, solver = _build_solver(game_name, family=family, params=params)
    _advance_solver(solver, family, resolved_iterations)
    policy = _average_policy(solver, family)
    metadata = PolicySnapshotMetadata(
        game=game_name,
        algorithm=family,
        family=family,
        params=params,
        iterations=resolved_iterations,
        transformed_to_turn_based=transformed,
        built_at=datetime.now(timezone.utc).isoformat(),
    )
    with output.open("wb") as handle:
        pickle.dump({"metadata": metadata.model_dump(mode="json"), "policy": policy}, handle)
    return PolicyBuildReport(
        game=game_name,
        generator_name=generator_name,
        generator_family=family,
        output=str(output),
        iterations=resolved_iterations,
        params=params,
        transformed_to_turn_based=transformed,
    )


def load_policy_snapshot(path: str) -> tuple[LoadedPolicySnapshot, object]:
    target = Path(path)
    with target.open("rb") as handle:
        payload = pickle.load(handle)
    metadata = PolicySnapshotMetadata.model_validate(payload["metadata"])
    return LoadedPolicySnapshot(metadata=metadata, policy_path=str(target)), payload["policy"]


def policy_status(*, game_name: str, generator_name: str, family: str, policy_path: str) -> PolicyStatusEntry:
    path = Path(policy_path)
    return PolicyStatusEntry(
        game=game_name,
        generator_name=generator_name,
        generator_family=family,
        policy_path=str(path),
        exists=path.exists(),
        reason="" if path.exists() else "policy snapshot missing",
    )


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


def _policy_record(
    *,
    game_name: str,
    seed: int,
    snapshot: LoadedPolicySnapshot,
    policy,
) -> dict | None:
    import numpy as np
    import pyspiel

    ensure_game_scripts_path()
    from generate_v11 import GAME_IDX, GAME_RULES, SYSTEM_PROMPT_TEMPLATE, make_user_prompt  # type: ignore

    random.seed(seed)
    np.random.seed(seed % (2**31))

    base_game = pyspiel.load_game(game_name, snapshot.metadata.params)
    if snapshot.metadata.transformed_to_turn_based:
        game = pyspiel.convert_to_turn_based(base_game)
    else:
        game = base_game
    state = game.new_initial_state()
    bot_player = random.randint(0, game.num_players() - 1)

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        game_name=game_name,
        rules=GAME_RULES[game_name],
    )
    messages = [{"role": "system", "content": system_prompt}]

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
                    messages.append({"role": "user", "content": make_user_prompt(state, player, legal, game_name)})
                    messages.append({"role": "assistant", "content": str(action)})
                actions.append(action)
            state.apply_actions(actions)
        else:
            current_player = state.current_player()
            legal = state.legal_actions(current_player)
            if current_player == bot_player:
                action = _policy_action(policy, state)
                if action not in legal:
                    raise RuntimeError(f"{game_name} policy generator returned invalid action {action}")
                messages.append({"role": "user", "content": make_user_prompt(state, current_player, legal, game_name)})
                messages.append({"role": "assistant", "content": str(action)})
                state.apply_action(action)
            else:
                state.apply_action(random.choice(legal))
        move_count += 1

    if not state.is_terminal() or len(messages) < 3:
        return None

    returns = state.returns()
    score = max(0.0, min(1.0, (returns[bot_player] + 1) / 2.0))
    if score < 0.5:
        return None

    config_id = random.randint(0, 99_999_999)
    return {
        "messages": messages,
        "env": "GAME",
        "source": f"{snapshot.metadata.family}_snapshot",
        "game": game_name,
        "score": score,
        "task_id": GAME_IDX[game_name] * 100_000_000 + config_id,
        "seed": seed,
    }


class PolicySnapshotTrajectoryGenerator:
    """Read-only policy-snapshot generator for imperfect-information games."""

    def __init__(self, *, name: str, family: str, policy_path: str):
        self.name = name
        self.family = family
        self.policy_path = policy_path

    def generate_batch(
        self,
        *,
        game_name: str,
        output_path: str,
        sample_count: int,
        start_seed: int,
        attempt_multiplier: int = 4,
    ) -> GameTrajectoryGeneratorReport:
        target = Path(self.policy_path)
        if not target.exists():
            raise FileNotFoundError(
                f"GAME policy snapshot missing for {game_name}: {target}. "
                f"Run `orbit data game-build-policy --game {game_name}` first."
            )

        snapshot, policy = load_policy_snapshot(str(target))
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("", encoding="utf-8")

        attempts = 0
        max_attempts = max(sample_count * max(attempt_multiplier, 1), sample_count)
        seed_rng = game_seed_rng(game_name, start_seed)

        while count_jsonl_records(output) < sample_count and attempts < max_attempts:
            seed = seed_rng.randint(0, max(1, 2**31 - 2))
            record = _policy_record(
                game_name=game_name,
                seed=seed,
                snapshot=snapshot,
                policy=policy,
            )
            attempts += 1
            if record:
                append_jsonl_record(output, record)

        wins = count_jsonl_records(output)
        return GameTrajectoryGeneratorReport(
            game=game_name,
            generator_name=self.name,
            generator_family=self.family,
            output=str(output),
            records=wins,
            wins=wins,
            attempts=attempts,
            mode="policy",
        )


def default_policy_path(game_name: str, family: str) -> str:
    from orbit.data.game_generators.base import POLICY_ROOT

    return str(POLICY_ROOT / game_name / family / "policy.pkl")
