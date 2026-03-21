#!/usr/bin/env python3
"""
GAME Bot data generator — bot vs MCTS opponent (matching eval).

CRITICAL: Opponent is MCTS, NOT random. This matches eval conditions.
For simultaneous games (goofspiel), MCTS not supported → uses random (same as eval).

Usage:
    PYTHONPATH=.pylibs OPENSPIEL_DIR=repos/affinetes/environments/openspiel \
        python3 scripts/game/game_bot_gen_mcts.py --game leduc_poker -n 100

On GPU:
    PYTHONPATH=/root/game_gen:/root/game_gen/game OPENSPIEL_DIR=/root/affinetes/environments/openspiel \
        python3 /root/game_gen/game/game_bot_gen_mcts.py --game leduc_poker -n 100
"""

import argparse
import json
import random
import sys
import os
import math
import numpy as np
from pathlib import Path

# Setup paths
_dir = os.path.dirname(os.path.abspath(__file__))
_project = os.path.dirname(os.path.dirname(_dir))
_openspiel = os.environ.get("OPENSPIEL_DIR", os.path.join(_project, "repos", "affinetes", "environments", "openspiel"))
sys.path.insert(0, _openspiel)
sys.path.insert(0, _dir)
sys.path.insert(0, os.path.join(_project, "scripts"))

import pyspiel
from open_spiel.python.algorithms import mcts


# --- MCTS Evaluator (identical to eval's SafeRandomRolloutEvaluator) ---
class SafeRandomRolloutEvaluator(mcts.Evaluator):
    def __init__(self, n_rollouts=1, random_state=None):
        self._n = n_rollouts
        self._rs = random_state or np.random.RandomState()

    def evaluate(self, state):
        if state.is_terminal(): return state.returns()
        la = state.legal_actions()
        if not la: return state.returns()
        t = np.zeros(state.num_players())
        for _ in range(self._n):
            ws = state.clone()
            while not ws.is_terminal():
                a = ws.legal_actions()
                if not a: break
                ws.apply_action(self._rs.choice(a))
            t += ws.returns()
        return t / self._n

    def prior(self, state):
        la = state.legal_actions()
        return [(a, 1.0/len(la)) for a in la] if la else []


def _create_mcts_opponent(game, seed, agent_inst):
    """Create MCTS opponent with eval-matching config."""
    cfg = agent_inst.get_mcts_config() if agent_inst else None
    if cfg is None:
        return None
    max_sim, n_roll = cfg
    evaluator = SafeRandomRolloutEvaluator(n_rollouts=n_roll, random_state=np.random.RandomState(seed + 5))
    return mcts.MCTSBot(game=game, uct_c=1.414, max_simulations=max_sim,
                        evaluator=evaluator, random_state=np.random.RandomState(seed + 6))


def generate_game_trajectory(game_name, seed, bot_func):
    """Run bot vs MCTS. Returns record for both wins AND losses."""
    from game_config import AVAILABLE_GAMES, generate_game_params
    from agents import GAME_AGENTS

    random.seed(seed)
    game_idx = AVAILABLE_GAMES.index(game_name)
    config_id = random.randint(0, 99_999_999)
    game_params = generate_game_params(game_name, config_id)
    game = pyspiel.load_game(game_name, game_params)
    state = game.new_initial_state()
    bot_player = random.randint(0, game.num_players() - 1)

    # System prompt = eval
    agent_class = GAME_AGENTS.get(game_name)
    agent_inst = agent_class() if agent_class else None
    system_prompt = agent_inst.generate_system_prompt() if agent_inst else f"You are playing {game_name}.\nrespond with ONLY the action ID number."
    messages = [{"role": "system", "content": system_prompt}]

    # MCTS opponent
    mcts_opp = None
    if game.get_type().dynamics != pyspiel.GameType.Dynamics.SIMULTANEOUS:
        mcts_opp = _create_mcts_opponent(game, seed, agent_inst)

    move_count = 0
    while not state.is_terminal() and move_count < 500:
        if state.is_chance_node():
            outcomes = state.chance_outcomes()
            state.apply_action(random.choices([a for a, _ in outcomes], [p for _, p in outcomes])[0])
            continue

        if state.is_simultaneous_node():
            actions = []
            for p in range(game.num_players()):
                p_legal = state.legal_actions(p)
                if p == bot_player:
                    action, think = bot_func(state, p)
                    if action not in p_legal: action = p_legal[0]
                    try: user_content = agent_inst.generate_user_prompt(state, p, p_legal)
                    except:
                        try: obs = agent_inst.format_state(state, p)
                        except: obs = str(state)
                        user_content = f"Current State:\n{obs}\n\nLegal Actions:\n" + "\n".join(f"{a} -> {state.action_to_string(p, a)}" for a in p_legal)
                    messages.append({"role": "user", "content": user_content})
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
                try: user_content = agent_inst.generate_user_prompt(state, cp, legal)
                except:
                    try: obs = agent_inst.format_state(state, cp)
                    except: obs = str(state)
                    user_content = f"Current State:\n{obs}\n\nLegal Actions:\n" + "\n".join(f"{a} -> {state.action_to_string(cp, a)}" for a in legal)
                messages.append({"role": "user", "content": user_content})
                messages.append({"role": "assistant", "content": f"<think>{think}</think>\n{action}"})
                state.apply_action(action)
            else:
                # OPPONENT: MCTS (matching eval)
                if mcts_opp:
                    action = mcts_opp.step(state)
                else:
                    action = random.choice(legal)
                state.apply_action(action)
        move_count += 1

    if state.is_terminal() and len(messages) >= 3:
        returns = state.returns()
        score = max(0, min(1, (returns[bot_player] + 1) / 2.0))
        return {
            "messages": messages, "env": "GAME", "source": "bot_strategy",
            "game": game_name, "score": score,
            "task_id": game_idx * 100_000_000 + config_id, "seed": seed,
            "won": score >= 0.5,
        }
    return None


def main():
    # Import bots - try per-game file first, fall back to game_bots
    try:
        from game_bots import BOTS
    except:
        BOTS = {}

    # Override with per-game bot files
    for game_name in ["goofspiel", "leduc_poker", "liars_dice", "gin_rummy", "othello", "hex", "clobber"]:
        try:
            mod = __import__(f"{game_name}_bot")
            BOTS[game_name] = getattr(mod, f"{game_name}_bot")
        except:
            pass

    parser = argparse.ArgumentParser(description="GAME Bot vs MCTS data generation")
    parser.add_argument("--game", required=True, choices=list(BOTS.keys()))
    parser.add_argument("-n", "--count", type=int, default=20)
    parser.add_argument("-o", "--output", default=None)
    parser.add_argument("--start-seed", type=int, default=100000)
    args = parser.parse_args()

    if args.output is None:
        args.output = f"data/game_mcts_{args.game}.jsonl"

    os.chdir(_openspiel)
    bot_func = BOTS[args.game]
    output_path = os.path.join(_project, args.output)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    losses_path = output_path.replace(".jsonl", "_losses.jsonl")

    wins, losses = 0, 0
    for i in range(args.count):
        seed = args.start_seed + i
        try:
            record = generate_game_trajectory(args.game, seed, bot_func)
            if record:
                path = output_path if record["won"] else losses_path
                with open(path, "a") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                if record["won"]: wins += 1
                else: losses += 1
            else:
                losses += 1
        except Exception as e:
            losses += 1
            if i < 3: print(f"  seed={seed} error: {e}")

    rate = wins * 100 // max(wins + losses, 1)
    print(f"{args.game}: {wins}W {losses}L ({rate}%) vs MCTS")
    print(f"Wins: {output_path}")
    print(f"Losses: {losses_path}")


if __name__ == "__main__":
    main()
