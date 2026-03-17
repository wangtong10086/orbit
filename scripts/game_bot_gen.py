#!/usr/bin/env python3
"""
GAME Strategy Bot data generator

Uses programmatic strategy bots to play games, generating training data with <think> tags.

Usage:
    python3 scripts/game_bot_gen.py --game leduc_poker -n 100 -o data/game_bot_leduc.jsonl
    python3 scripts/game_bot_gen.py --game liars_dice -n 100
"""

import argparse
import json
import random
import sys
import os
from pathlib import Path

sys.path.insert(0, os.environ.get("OPENSPIEL_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "affinetes", "environments", "openspiel")))
# Also add scripts/ dir so game_bots is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyspiel

from game_bots import BOTS


# ============================================================================
# Data generation: run OpenSpiel with bot, record full trajectories
# ============================================================================

def generate_game_trajectory(game_name, seed, bot_func):
    """Run a game with bot vs random, return SFT record if bot wins."""
    from game_config import AVAILABLE_GAMES, generate_game_params
    from agents import GAME_AGENTS

    random.seed(seed)

    # Create game
    game_idx = AVAILABLE_GAMES.index(game_name)
    config_id = random.randint(0, 99_999_999)
    game_params = generate_game_params(game_name, config_id)
    game = pyspiel.load_game(game_name, game_params)

    state = game.new_initial_state()
    bot_player = random.randint(0, game.num_players() - 1)

    # Build conversation
    messages = []

    # System prompt (same as DDB/evaluation)
    agent_class = GAME_AGENTS.get(game_name)
    if agent_class:
        agent_inst = agent_class()
        system_prompt = agent_inst.generate_system_prompt()
    else:
        agent_inst = None
        system_prompt = f"You are playing {game_name}.\nrespond with ONLY the action ID number."
    messages.append({"role": "system", "content": system_prompt})

    # Play game
    move_count = 0
    max_moves = 500

    while not state.is_terminal() and move_count < max_moves:
        if state.is_chance_node():
            outcomes = state.chance_outcomes()
            action = random.choices(
                [a for a, _ in outcomes],
                weights=[p for _, p in outcomes]
            )[0]
            state.apply_action(action)
            continue

        if state.is_simultaneous_node():
            # Simultaneous game (e.g. goofspiel): all players act at once
            actions = []
            for p in range(game.num_players()):
                p_legal = state.legal_actions(p)
                if p == bot_player:
                    action, think = bot_func(state, p)
                    if action not in p_legal:
                        action = p_legal[0]
                    # Record bot's move using agent's format
                    try:
                        user_content = agent_inst.generate_user_prompt(state, p, p_legal)
                    except Exception:
                        try:
                            obs = agent_inst.format_state(state, p)
                        except Exception:
                            obs = str(state)
                        legal_str = "\n".join(f"{a} -> {state.action_to_string(p, a)}" for a in p_legal)
                        user_content = f"Current State:\n{obs}\n\nLegal Actions:\n{legal_str}\n\nYour choice (ID only):"
                    messages.append({"role": "user", "content": user_content})
                    messages.append({"role": "assistant", "content": f"<think>{think}</think>\n{action}"})
                    actions.append(action)
                else:
                    actions.append(random.choice(p_legal))
            state.apply_actions(actions)
        else:
            current_player = state.current_player()
            legal = state.legal_actions(current_player)

            if current_player == bot_player:
                # Bot plays
                action, think = bot_func(state, current_player)
                if action not in legal:
                    action = legal[0]

                # Build user message using agent's format (matches DDB/evaluation exactly)
                try:
                    user_content = agent_inst.generate_user_prompt(state, current_player, legal)
                except Exception:
                    try:
                        obs = agent_inst.format_state(state, current_player)
                    except Exception:
                        obs = str(state)
                    legal_str = "\n".join(f"{a} -> {state.action_to_string(current_player, a)}" for a in legal)
                    user_content = f"Current State:\n{obs}\n\nLegal Actions:\n{legal_str}\n\nYour choice (ID only):"
                messages.append({"role": "user", "content": user_content})
                messages.append({"role": "assistant", "content": f"<think>{think}</think>\n{action}"})

                state.apply_action(action)
            else:
                # Opponent: use random policy
                action = random.choice(legal)
                state.apply_action(action)

        move_count += 1

    if state.is_terminal():
        returns = state.returns()
        score = (returns[bot_player] + 1) / 2.0  # normalize to 0-1
        score = max(0, min(1, score))

        if score >= 0.5 and len(messages) >= 3:
            task_id = game_idx * 100_000_000 + config_id
            return {
                "messages": messages,
                "env": "GAME",
                "source": "bot_strategy",
                "game": game_name,
                "score": score,
                "task_id": task_id,
                "seed": seed,
            }
    return None


def main():
    parser = argparse.ArgumentParser(description="GAME Bot data generation")
    parser.add_argument("--game", required=True, choices=list(BOTS.keys()))
    parser.add_argument("-n", "--count", type=int, default=100)
    parser.add_argument("-o", "--output", default=None)
    parser.add_argument("--start-seed", type=int, default=100000)
    args = parser.parse_args()

    if args.output is None:
        args.output = f"data/game_bot_{args.game}.jsonl"

    openspiel_dir = os.environ.get("OPENSPIEL_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "affinetes", "environments", "openspiel"))
    os.chdir(openspiel_dir)
    bot_func = BOTS[args.game]
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    # Use absolute path since we chdir
    project_dir = os.environ.get("AFFINE_FORGE_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    output_path = os.path.join(project_dir, args.output)

    success = 0
    failed = 0
    for i in range(args.count):
        seed = args.start_seed + i
        try:
            record = generate_game_trajectory(args.game, seed, bot_func)
            if record:
                with open(output_path, "a") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                success += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            if i < 3:
                print(f"  seed={seed} error: {e}")

    print(f"{args.game}: {success} wins / {failed} losses (total {args.count})")
    print(f"Win rate: {success * 100 // max(args.count, 1)}%")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
