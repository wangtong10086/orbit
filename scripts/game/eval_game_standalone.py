#!/usr/bin/env python3
"""Standalone GAME eval script — runs directly on host, no Docker.

Matches original eval logic exactly:
- Same game configs, agents, MCTS opponents
- Same scoring (normalized game returns)
- Same conversation history management
- Same retry mechanism

Additional: captures reasoning_content (think blocks) for analysis.

Usage:
    python3 eval_game_standalone.py --base-url http://localhost:30000/v1 --model /root/merged_model --samples 100
    python3 eval_game_standalone.py --samples 20 --games othello,hex  # specific games only
    python3 eval_game_standalone.py --samples 5 --keep-think  # don't strip think from conversation history
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
import random
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional, Dict, List, Any

# Add paths
_dir = os.path.dirname(os.path.abspath(__file__))
_project = os.path.dirname(os.path.dirname(_dir))
_openspiel = os.path.join(_project, "repos", "affinetes", "environments", "openspiel")
_affinetes = os.path.join(_project, "repos", "affinetes")
sys.path.insert(0, _openspiel)
sys.path.insert(0, _affinetes)

import pyspiel
import openai
from agents import GAME_AGENTS

# Game configs matching eval
GAME_CONFIGS = {
    "goofspiel": {"idx": 0, "opponent": "random"},
    "liars_dice": {"idx": 1, "opponent": "mcts", "mcts_sim": 3000, "mcts_roll": 200},
    "leduc_poker": {"idx": 2, "opponent": "mcts", "mcts_sim": 3000, "mcts_roll": 200},
    "gin_rummy": {"idx": 3, "opponent": "mcts", "mcts_sim": 500, "mcts_roll": 10},
    "othello": {"idx": 4, "opponent": "mcts", "mcts_sim": 1000, "mcts_roll": 20},
    "hex": {"idx": 6, "opponent": "mcts", "mcts_sim": 1000, "mcts_roll": 50},
    "clobber": {"idx": 7, "opponent": "mcts", "mcts_sim": 1500, "mcts_roll": 100},
}

MAX_RETRIES = 2


def remove_think_tags(text):
    """Same as affinetes.core.llm_chat.remove_think_tags"""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"<thinking>.*?</thinking>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if "</think>" in cleaned:
        cleaned = cleaned.split("</think>")[-1]
    if "</thinking>" in cleaned:
        cleaned = cleaned.split("</thinking>")[-1]
    for tag in ("<think>", "<thinking>"):
        match = re.search(tag, cleaned, flags=re.IGNORECASE)
        if match:
            cleaned = cleaned[:match.start()]
    cleaned = re.sub(r"\n\s*\n\s*\n", "\n\n", cleaned)
    return cleaned.strip()


def create_mcts_opponent(game, game_name):
    """Create MCTS opponent matching eval config."""
    cfg = GAME_CONFIGS[game_name]
    if cfg["opponent"] != "mcts":
        return None
    try:
        from open_spiel.python.algorithms import mcts as mcts_lib

        class Evaluator(mcts_lib.Evaluator):
            def __init__(self, n_rollouts):
                self._n = n_rollouts
                self._rs = np.random.RandomState(42)

            def evaluate(self, state):
                if state.is_terminal():
                    return state.returns()
                t = np.zeros(state.num_players())
                for _ in range(self._n):
                    ws = state.clone()
                    while not ws.is_terminal():
                        a = ws.legal_actions()
                        if not a:
                            break
                        ws.apply_action(self._rs.choice(a))
                    t += ws.returns()
                return t / self._n

            def prior(self, state):
                la = state.legal_actions()
                return [(a, 1.0 / len(la)) for a in la] if la else []

        return mcts_lib.MCTSBot(
            game=game, uct_c=1.414,
            max_simulations=cfg["mcts_sim"],
            evaluator=Evaluator(n_rollouts=cfg["mcts_roll"]),
            random_state=np.random.RandomState(123),
            solve=True,
        )
    except Exception as e:
        print(f"  MCTS opponent failed for {game_name}: {e}")
        return None


def parse_action(response, legal_actions, state, player_id):
    """Parse action from model response — same logic as llm_bot.py"""
    response_clean = response.strip()

    # Strategy 1: Pure number
    if match := re.search(r'^\s*(\d+)\s*$', response_clean):
        action = int(match.group(1))
        if action in legal_actions:
            return action
        return None

    # Strategy 2: Find legal action ID in text
    for action in legal_actions:
        if re.search(rf'\b{action}\b', response_clean):
            return action

    return None


def call_llm(client, model, messages, temperature=0, keep_think=False):
    """Call LLM API, return (stripped_content, raw_content)."""
    resp = client.chat.completions.create(
        model=model, messages=messages,
        max_tokens=2000, temperature=temperature,
    )
    raw = resp.choices[0].message.content or ""
    if keep_think:
        stripped = raw  # don't strip — let model see its own thinking
    else:
        stripped = remove_think_tags(raw).strip() if raw else ""
    return stripped, raw


def play_one_game(game_name, seed, client, model, temperature=0, keep_think=False):
    """Play one game, return result dict."""
    agent = GAME_AGENTS[game_name]()
    params = agent.generate_params(seed % 100_000_000)
    game = pyspiel.load_game(game_name, params)
    state = game.new_initial_state()

    rng = random.Random(seed)
    np_rng = np.random.RandomState(seed % (2**31))
    llm_player = rng.randint(0, game.num_players() - 1)

    # Create MCTS opponent
    mcts_opp = create_mcts_opponent(game, game_name)

    system_prompt = agent.generate_system_prompt()
    conversation = [{"role": "system", "content": system_prompt}]
    all_thinks = []  # collect all thinking content

    move_count = 0
    start_time = time.time()

    while not state.is_terminal() and move_count < 500:
        if state.is_chance_node():
            outcomes = state.chance_outcomes()
            state.apply_action(rng.choices(
                [a for a, _ in outcomes], [p for _, p in outcomes])[0])
            continue

        if state.is_simultaneous_node():
            actions = []
            for p in range(game.num_players()):
                p_legal = state.legal_actions(p)
                if p == llm_player:
                    user_prompt = agent.generate_user_prompt(state, p, p_legal)
                    conversation.append({"role": "user", "content": user_prompt})

                    action = None
                    for attempt in range(MAX_RETRIES + 1):
                        stripped, raw = call_llm(client, model, conversation, temperature, keep_think)

                        # Store in conversation
                        msg = {"role": "assistant", "content": stripped}
                        if raw and raw != stripped:
                            msg["reasoning_content"] = raw
                            all_thinks.append(raw)
                        conversation.append(msg)

                        action = parse_action(stripped, p_legal, state, p)
                        if action is not None:
                            break
                        conversation.append({"role": "user", "content":
                            f"Invalid response format. You must respond with ONLY the action ID number. Attempt {attempt+1}/{MAX_RETRIES+1}."})

                    if action is None:
                        action = p_legal[0]
                    actions.append(action)
                else:
                    actions.append(rng.choice(p_legal))
            state.apply_actions(actions)
        else:
            cp = state.current_player()
            legal = state.legal_actions(cp)
            if cp == llm_player:
                user_prompt = agent.generate_user_prompt(state, cp, legal)
                conversation.append({"role": "user", "content": user_prompt})

                action = None
                for attempt in range(MAX_RETRIES + 1):
                    stripped, raw = call_llm(client, model, conversation, temperature, keep_think)

                    msg = {"role": "assistant", "content": stripped}
                    if raw and raw != stripped:
                        msg["reasoning_content"] = raw
                        all_thinks.append(raw)
                    conversation.append(msg)

                    action = parse_action(stripped, legal, state, cp)
                    if action is not None:
                        break
                    conversation.append({"role": "user", "content":
                        f"Invalid response format. You must respond with ONLY the action ID number. Attempt {attempt+1}/{MAX_RETRIES+1}."})

                if action is None:
                    action = legal[0]
                state.apply_action(action)
            else:
                # Opponent move
                if mcts_opp:
                    try:
                        opp_action = mcts_opp.step(state)
                        if opp_action in legal:
                            state.apply_action(opp_action)
                        else:
                            state.apply_action(rng.choice(legal))
                    except:
                        state.apply_action(rng.choice(legal))
                else:
                    state.apply_action(rng.choice(legal))
        move_count += 1

    elapsed = time.time() - start_time
    score = 0.0
    if state.is_terminal():
        returns = state.returns()
        score = max(0, min(1, (returns[llm_player] + 1) / 2.0))

    return {
        "game": game_name,
        "seed": seed,
        "score": score,
        "elapsed": elapsed,
        "thinks": len(all_thinks),
        "think_words": sum(len(t.split()) for t in all_thinks),
        "conversation": conversation,
        "all_thinks": all_thinks,
    }


def main():
    parser = argparse.ArgumentParser(description="Standalone GAME eval")
    parser.add_argument("--base-url", default="http://localhost:30000/v1")
    parser.add_argument("--model", default="/root/merged_model")
    parser.add_argument("--api-key", default="x")
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--temperature", type=float, default=0)
    parser.add_argument("--games", default=None, help="Comma-separated game names")
    parser.add_argument("--output", default="eval_game_standalone.json")
    parser.add_argument("--keep-think", action="store_true",
                       help="Keep think blocks in conversation history (model sees its own thinking)")
    parser.add_argument("--seed-start", type=int, default=0)
    args = parser.parse_args()

    client = openai.OpenAI(base_url=args.base_url, api_key=args.api_key)

    if args.games:
        games = args.games.split(",")
    else:
        games = list(GAME_CONFIGS.keys())

    # Generate task list matching eval distribution
    tasks = []
    for i in range(args.samples):
        seed = args.seed_start + i
        rng = random.Random(seed)
        game = rng.choice(games)
        tasks.append((game, seed))

    results = []
    for i, (game_name, seed) in enumerate(tasks):
        try:
            result = play_one_game(game_name, seed, client, args.model,
                                   args.temperature, args.keep_think)
            results.append(result)
            thinks_info = f"thinks={result['thinks']}" if result['thinks'] > 0 else "no-think"
            print(f"[{i+1}/{len(tasks)}] {game_name}: score={result['score']:.2f} "
                  f"({result['elapsed']:.1f}s) {thinks_info}")

            # Incremental save
            with open(args.output + "l", "a") as f:
                summary = {k: v for k, v in result.items() if k != "conversation"}
                f.write(json.dumps(summary, ensure_ascii=False, default=str) + "\n")
        except Exception as e:
            print(f"[{i+1}/{len(tasks)}] {game_name}: ERROR {e}")
            results.append({"game": game_name, "seed": seed, "score": 0, "error": str(e)})

    # Final summary
    from collections import defaultdict
    game_scores = defaultdict(list)
    for r in results:
        game_scores[r["game"]].append(r["score"])

    print(f"\n{'='*50}")
    print(f"Results ({len(results)} samples, keep_think={args.keep_think}):")
    all_scores = []
    for g in games:
        s = game_scores.get(g, [])
        all_scores.extend(s)
        avg = sum(s) / len(s) * 100 if s else 0
        nz = sum(1 for x in s if x > 0)
        thinks = sum(1 for r in results if r["game"] == g and r.get("thinks", 0) > 0)
        print(f"  {g:15s} {avg:5.1f}% ({nz}/{len(s)}) thinks={thinks}")
    if all_scores:
        print(f"  {'TOTAL':15s} {sum(all_scores)/len(all_scores)*100:5.1f}%")

    # Save full results
    with open(args.output, "w") as f:
        json.dump({"results": results, "args": vars(args)}, f, ensure_ascii=False, default=str)
    print(f"\nSaved to {args.output}")


if __name__ == "__main__":
    main()
