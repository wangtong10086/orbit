"""Search-based GAME trajectory generators for perfect-information games."""

from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import pyspiel

from forge.data.game_generators.base import (
    GameTrajectoryGeneratorReport,
    append_jsonl_record,
    count_jsonl_records,
    ensure_game_scripts_path,
    game_seed_rng,
)


ensure_game_scripts_path()

from generate_v11 import (  # type: ignore  # noqa: E402
    GAME_IDX,
    GAME_RULES,
    SYSTEM_PROMPT_TEMPLATE,
    clobber_filter_opening,
    hex_opening_action,
    make_mcts_bot,
    make_user_prompt,
)


SEARCH_BUDGETS = {
    "othello": {"sim": 300, "roll": 5},
    "hex": {"sim": 300, "roll": 10},
    "clobber": {"sim": 400, "roll": 5},
}


def _search_record(*, game_name: str, seed: int, game_params: dict) -> dict | None:
    random.seed(seed)
    np.random.seed(seed % (2**31))

    game = pyspiel.load_game(game_name, game_params)
    state = game.new_initial_state()
    bot_player = random.randint(0, game.num_players() - 1)

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        game_name=game_name,
        rules=GAME_RULES[game_name],
    )
    messages = [{"role": "system", "content": system_prompt}]
    budget = SEARCH_BUDGETS[game_name]
    bot = make_mcts_bot(game, budget["sim"], budget["roll"], seed=seed % (2**31))

    move_count = 0
    while not state.is_terminal() and move_count < 500:
        if state.is_chance_node():
            outcomes = state.chance_outcomes()
            state.apply_action(random.choices([a for a, _ in outcomes], [p for _, p in outcomes])[0])
            continue

        current_player = state.current_player()
        legal = state.legal_actions(current_player)
        if not legal:
            break

        if current_player == bot_player:
            if game_name == "hex":
                board_size = int(game_params.get("board_size", 7))
                action = hex_opening_action(state, current_player, board_size)
                if action is None:
                    action = bot.step(state)
            elif game_name == "clobber":
                action = bot.step(state)
                if not clobber_filter_opening(state, current_player, action):
                    replacement = None
                    for candidate in legal:
                        if clobber_filter_opening(state, current_player, candidate):
                            replacement = candidate
                            break
                    if replacement is not None:
                        action = replacement
            else:
                action = bot.step(state)

            if action not in legal:
                raise RuntimeError(f"{game_name} search generator returned invalid action {action}")

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
        "source": "search_policy",
        "game": game_name,
        "score": score,
        "task_id": GAME_IDX[game_name] * 100_000_000 + config_id,
        "seed": seed,
    }


class SearchTrajectoryGenerator:
    """Collection-time search generator with bounded MCTS budgets."""

    def __init__(self, *, name: str, family: str, game_params: dict[str, object]):
        self.name = name
        self.family = family
        self.game_params = dict(game_params)

    def generate_batch(
        self,
        *,
        game_name: str,
        output_path: str,
        sample_count: int,
        start_seed: int,
        attempt_multiplier: int = 4,
    ) -> GameTrajectoryGeneratorReport:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("", encoding="utf-8")

        attempts = 0
        max_attempts = max(sample_count * max(attempt_multiplier, 1), sample_count)
        seed_rng = game_seed_rng(game_name, start_seed)

        while count_jsonl_records(output) < sample_count and attempts < max_attempts:
            seed = seed_rng.randint(0, max(1, 2**31 - 2))
            record = _search_record(
                game_name=game_name,
                seed=seed,
                game_params=self.game_params,
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
            mode="search",
        )
