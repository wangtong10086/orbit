#!/usr/bin/env python3
"""Fast data generation: improved bot vs RANDOM opponent.

v2.7 proved: bot vs random data teaches model effectively.
gin_rummy bot 0% vs MCTS, but model scored 47.6% with vs-random data.
Model generalizes better than bot.

This generator uses RANDOM opponent (fast) with improved bot strategies
that produce high-quality think blocks.

Usage:
    python3 scripts/game/generate_fast.py --game leduc_poker -n 500
    python3 scripts/game/generate_fast.py --all -n 200
"""

import argparse
import json
import os
import random
import sys

_dir = os.path.dirname(os.path.abspath(__file__))
_project = os.path.dirname(os.path.dirname(_dir))
_openspiel = os.environ.get("OPENSPIEL_DIR",
    os.path.join(_project, "repos", "affinetes", "environments", "openspiel"))
sys.path.insert(0, _openspiel)
sys.path.insert(0, _dir)
sys.path.insert(0, os.path.join(_project, "scripts"))

import pyspiel
from game_config import AVAILABLE_GAMES, generate_game_params
from agents import GAME_AGENTS

# Load all bots (per-game files override game_bots.py)
BOTS = {}
try:
    from game_bots import BOTS as _base
    BOTS.update(_base)
except:
    pass
for gn in ["goofspiel", "leduc_poker", "liars_dice", "gin_rummy", "othello", "hex", "clobber"]:
    try:
        mod = __import__(f"{gn}_bot")
        BOTS[gn] = getattr(mod, f"{gn}_bot")
    except:
        pass


def generate_one(game_name, seed):
    """Play bot vs random. Returns record (win or loss)."""
    random.seed(seed)
    game_idx = AVAILABLE_GAMES.index(game_name)
    config_id = random.randint(0, 99_999_999)
    game_params = generate_game_params(game_name, config_id)
    game = pyspiel.load_game(game_name, game_params)
    state = game.new_initial_state()
    bot_player = random.randint(0, game.num_players() - 1)

    agent_class = GAME_AGENTS.get(game_name)
    agent_inst = agent_class() if agent_class else None
    system_prompt = agent_inst.generate_system_prompt() if agent_inst else \
        f"You are playing {game_name}.\nrespond with ONLY the action ID number."
    messages = [{"role": "system", "content": system_prompt}]
    bot_func = BOTS[game_name]

    move_count = 0
    while not state.is_terminal() and move_count < 500:
        if state.is_chance_node():
            outcomes = state.chance_outcomes()
            state.apply_action(random.choices(
                [a for a, _ in outcomes], [p for _, p in outcomes])[0])
            continue

        if state.is_simultaneous_node():
            actions = []
            for p in range(game.num_players()):
                p_legal = state.legal_actions(p)
                if p == bot_player:
                    action, think = bot_func(state, p)
                    if action not in p_legal: action = p_legal[0]
                    try: uc = agent_inst.generate_user_prompt(state, p, p_legal)
                    except:
                        try: obs = agent_inst.format_state(state, p)
                        except: obs = str(state)
                        uc = f"Current State:\n{obs}\n\nLegal Actions:\n" + \
                             "\n".join(f"{a} -> {state.action_to_string(p, a)}" for a in p_legal)
                    messages.append({"role": "user", "content": uc})
                    messages.append({"role": "assistant", "content": f"<think>{think}</think>\n{action}"})
                    actions.append(action)
                else:
                    actions.append(random.choice(p_legal))
            state.apply_actions(actions)
        else:
            cp = state.current_player()
            legal = state.legal_actions(cp)
            if cp == bot_player:
                action, think = bot_func(state, cp)
                if action not in legal: action = legal[0]
                try: uc = agent_inst.generate_user_prompt(state, cp, legal)
                except:
                    try: obs = agent_inst.format_state(state, cp)
                    except: obs = str(state)
                    uc = f"Current State:\n{obs}\n\nLegal Actions:\n" + \
                         "\n".join(f"{a} -> {state.action_to_string(cp, a)}" for a in legal)
                messages.append({"role": "user", "content": uc})
                messages.append({"role": "assistant", "content": f"<think>{think}</think>\n{action}"})
                state.apply_action(action)
            else:
                state.apply_action(random.choice(legal))
        move_count += 1

    if state.is_terminal() and len(messages) >= 3:
        returns = state.returns()
        score = max(0, min(1, (returns[bot_player] + 1) / 2.0))
        if score >= 0.5:  # only winning games
            return {
                "messages": messages, "env": "GAME", "source": "bot_strategy",
                "game": game_name, "score": score,
                "task_id": game_idx * 100_000_000 + config_id, "seed": seed,
            }
    return None


def main():
    parser = argparse.ArgumentParser(description="Fast bot vs random data generation")
    all_games = list(BOTS.keys())
    parser.add_argument("--game", choices=all_games)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("-n", default=200, type=int, help="Seeds per game")
    parser.add_argument("-o", "--output", default=None)
    parser.add_argument("--start-seed", default=100000, type=int)
    args = parser.parse_args()

    games = all_games if args.all else ([args.game] if args.game else [])
    if not games:
        parser.error("Specify --game or --all")

    os.chdir(_openspiel)

    for game_name in games:
        output = args.output or os.path.join(_project, f"data/game_final_{game_name}.jsonl")
        os.makedirs(os.path.dirname(output), exist_ok=True)

        wins, losses = 0, 0
        for i in range(args.n):
            seed = args.start_seed + i
            try:
                record = generate_one(game_name, seed)
                if record:
                    with open(output, "a") as f:
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    wins += 1
                else:
                    losses += 1
            except Exception as e:
                losses += 1
                if i < 3: print(f"  {game_name} seed={seed} error: {e}")

        rate = wins * 100 // max(wins + losses, 1)
        print(f"{game_name}: {wins}W {losses}L ({rate}%) → {output}")


if __name__ == "__main__":
    main()
