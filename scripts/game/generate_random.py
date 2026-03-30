#!/usr/bin/env python3
"""Fast GAME trajectory generation with random policies on both sides.

This is the current fallback collector path while stronger per-game
generators are being modularized and reintroduced incrementally.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys

import numpy as np
import pyspiel

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from generate_v11 import GAME_CONFIGS, GAME_IDX, GAME_RULES, SYSTEM_PROMPT_TEMPLATE, make_user_prompt


def generate_one(game_name: str, seed: int):
    random.seed(seed)
    np.random.seed(seed % (2**31))

    config_id = random.randint(0, 99_999_999)
    params = GAME_CONFIGS[game_name]()
    game = pyspiel.load_game(game_name, params)
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
            state.apply_action(random.choices(
                [a for a, _ in outcomes],
                [p for _, p in outcomes],
            )[0])
            continue

        if state.is_simultaneous_node():
            actions = []
            for player in range(game.num_players()):
                legal = state.legal_actions(player)
                action = random.choice(legal)
                if player == bot_player:
                    messages.append({"role": "user", "content": make_user_prompt(state, player, legal, game_name)})
                    messages.append({"role": "assistant", "content": str(action)})
                actions.append(action)
            state.apply_actions(actions)
        else:
            current_player = state.current_player()
            legal = state.legal_actions(current_player)
            action = random.choice(legal)
            if current_player == bot_player:
                messages.append({"role": "user", "content": make_user_prompt(state, current_player, legal, game_name)})
                messages.append({"role": "assistant", "content": str(action)})
            state.apply_action(action)

        move_count += 1

    if state.is_terminal() and len(messages) >= 3:
        returns = state.returns()
        score = max(0, min(1, (returns[bot_player] + 1) / 2.0))
        if score >= 0.5:
            return {
                "messages": messages,
                "env": "GAME",
                "source": "random_policy",
                "game": game_name,
                "score": score,
                "task_id": GAME_IDX[game_name] * 100_000_000 + config_id,
                "seed": seed,
            }
    return None


def main():
    parser = argparse.ArgumentParser(description="Random-policy GAME trajectory generation")
    parser.add_argument("--game", choices=list(GAME_CONFIGS.keys()))
    parser.add_argument("--all", action="store_true")
    parser.add_argument("-n", default=50, type=int)
    parser.add_argument("-o", "--output", default=None)
    parser.add_argument("--start-seed", default=100000, type=int)
    args = parser.parse_args()

    games = list(GAME_CONFIGS.keys()) if args.all else ([args.game] if args.game else [])
    if not games:
        parser.error("Specify --game or --all")

    for game_name in games:
        output = args.output or f"data/random_{game_name}.jsonl"
        os.makedirs(os.path.dirname(output) if os.path.dirname(output) else ".", exist_ok=True)

        wins, total = 0, 0
        with open(output, "a", encoding="utf-8") as handle:
            for index in range(args.n):
                seed = args.start_seed + index
                total += 1
                result = generate_one(game_name, seed)
                if result:
                    wins += 1
                    handle.write(json.dumps(result, ensure_ascii=False) + "\n")
                    handle.flush()
                if total % 10 == 0:
                    print(f"  {game_name}: {wins}W/{total} ({wins / total * 100:.0f}%)", flush=True)

        print(f"{game_name}: {wins}W/{total} ({wins / total * 100:.0f}%) → {output}")


if __name__ == "__main__":
    main()
