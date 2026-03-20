#!/usr/bin/env python3
"""
GAME LLM distillation — uses GPT-5.4 to play OpenSpiel games, generating high-quality SFT data.

Architecture:
  - Local pyspiel runs the game engine
  - LLM plays as one player (with <think> reasoning)
  - Random/MCTS plays as opponent
  - Only winning trajectories are saved

Usage:
    # Distill all 7 active games, 50 seeds each
    python3 scripts/game_distill.py --all -n 50

    # Specific games
    python3 scripts/game_distill.py --games othello,hex,clobber -n 100

    # Fast test
    python3 scripts/game_distill.py --games leduc_poker -n 5 --debug
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
import random
from pathlib import Path
from collections import Counter

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_DIR, ".pylibs"))

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_DIR, ".env"), override=True)

OPENSPIEL_DIR = os.path.join(PROJECT_DIR, "repos", "affinetes", "environments", "openspiel")
sys.path.insert(0, OPENSPIEL_DIR)

import pyspiel
import httpx

# Only the 7 evaluated games
ACTIVE_GAMES = {
    "goofspiel":   {"idx": 0, "params": {"num_cards": 13, "imp_info": True, "points_order": "descending"}},
    "liars_dice":  {"idx": 1, "params": {"players": 2, "numdice": 5}},
    "leduc_poker": {"idx": 2, "params": {}},
    "gin_rummy":   {"idx": 3, "params": {}},
    "othello":     {"idx": 4, "params": {}},
    "hex":         {"idx": 6, "params": {"board_size": 5}},
    "clobber":     {"idx": 7, "params": {"rows": 5, "columns": 5}},
}

API_KEY = os.environ.get("OPENAI_API_KEY", "")
BASE_URL = os.environ.get("OPENAI_BASE_URL", "")
MODEL = "gpt-5.4"


def get_agent(game_name):
    """Load the game agent for formatting prompts (same as eval uses)."""
    from agents import GAME_AGENTS
    agent_class = GAME_AGENTS.get(game_name)
    if agent_class:
        return agent_class()
    return None


def format_user_prompt(agent, state, player, legal_actions):
    """Format user prompt using the agent (matches eval format exactly)."""
    if agent:
        try:
            return agent.generate_user_prompt(state, player, legal_actions)
        except Exception:
            try:
                obs = agent.format_state(state, player)
            except Exception:
                obs = str(state)
            legal_str = "\n".join(f"{a} -> {state.action_to_string(player, a)}" for a in legal_actions)
            return f"Current State:\n{obs}\n\nLegal Actions:\n{legal_str}\n\nYour choice (ID only):"
    else:
        obs = str(state)
        legal_str = "\n".join(f"{a} -> {state.action_to_string(player, a)}" for a in legal_actions)
        return f"Current State:\n{obs}\n\nLegal Actions:\n{legal_str}\n\nYour choice (ID only):"


def get_system_prompt(agent, game_name):
    """Get system prompt using the agent (matches eval format) + think instruction."""
    base = None
    if agent:
        try:
            base = agent.generate_system_prompt()
        except Exception:
            pass
    if not base:
        base = f"You are playing {game_name}.\nrespond with ONLY the action ID number."

    # Add think block instruction (critical for GPT-5.4 which hides reasoning)
    think_instruction = (
        "\n\nYou MUST respond in exactly this format:\n"
        "<think>your strategic reasoning (1-3 sentences analyzing the game state)</think>\n"
        "ACTION_ID\n\n"
        "Always explain your strategy before choosing. Never skip the think block."
    )
    return base + think_instruction


def call_llm_sync(messages, legal_actions):
    """Call LLM API synchronously to get action + reasoning."""
    prompt_messages = list(messages)

    resp = httpx.post(
        f"{BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={"model": MODEL, "max_tokens": 500, "temperature": 0.7, "messages": prompt_messages},
        timeout=60.0,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"].strip()

    # Parse action from response
    # Expected format: <think>reasoning</think>\nACTION_ID
    # Or just: ACTION_ID
    think_match = re.search(r'<think>(.*?)</think>', content, re.DOTALL)

    # Extract number after think block (or anywhere in response)
    after_think = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
    numbers = re.findall(r'\b(\d+)\b', after_think)

    action = None
    if numbers:
        for num_str in numbers:
            num = int(num_str)
            if num in legal_actions:
                action = num
                break
        if action is None:
            action = int(numbers[0])  # take first number even if not legal

    # Build clean assistant response
    if think_match:
        think_text = think_match.group(1).strip()
        assistant_content = f"<think>{think_text}</think>\n{action if action is not None else numbers[0] if numbers else '0'}"
    else:
        # Wrap the whole response as think
        assistant_content = f"<think>{content[:300]}</think>\n{action if action is not None else '0'}"

    return action, assistant_content


def play_game(game_name, seed, debug=False):
    """Play one game: LLM vs random. Returns SFT record if LLM wins."""
    config = ACTIVE_GAMES[game_name]
    random.seed(seed)

    game = pyspiel.load_game(game_name, config["params"])
    state = game.new_initial_state()
    llm_player = random.randint(0, game.num_players() - 1)

    agent = get_agent(game_name)
    system_prompt = get_system_prompt(agent, game_name)

    # Build conversation for SFT
    messages = [{"role": "system", "content": system_prompt}]
    # Separate LLM context (includes think instruction)
    llm_context = [{"role": "system", "content": system_prompt}]

    move_count = 0
    max_moves = 500
    api_calls = 0

    while not state.is_terminal() and move_count < max_moves:
        if state.is_chance_node():
            outcomes = state.chance_outcomes()
            action = random.choices([a for a, _ in outcomes], weights=[p for _, p in outcomes])[0]
            state.apply_action(action)
            continue

        if state.is_simultaneous_node():
            actions = []
            for p in range(game.num_players()):
                p_legal = state.legal_actions(p)
                if p == llm_player:
                    user_content = format_user_prompt(agent, state, p, p_legal)
                    llm_context.append({"role": "user", "content": user_content})

                    action, asst_content = call_llm_sync(llm_context, p_legal)
                    api_calls += 1
                    if action not in p_legal:
                        action = random.choice(p_legal)

                    messages.append({"role": "user", "content": user_content})
                    messages.append({"role": "assistant", "content": asst_content})
                    llm_context.append({"role": "assistant", "content": asst_content})
                    actions.append(action)
                else:
                    actions.append(random.choice(p_legal))
            state.apply_actions(actions)
        else:
            current = state.current_player()
            legal = state.legal_actions(current)

            if current == llm_player:
                user_content = format_user_prompt(agent, state, current, legal)
                llm_context.append({"role": "user", "content": user_content})

                action, asst_content = call_llm_sync(llm_context, legal)
                api_calls += 1
                if action not in legal:
                    action = random.choice(legal)

                messages.append({"role": "user", "content": user_content})
                messages.append({"role": "assistant", "content": asst_content})
                llm_context.append({"role": "assistant", "content": asst_content})
                state.apply_action(action)
            else:
                action = random.choice(legal)
                state.apply_action(action)

        move_count += 1

    if not state.is_terminal():
        return None, api_calls

    returns = state.returns()
    score = (returns[llm_player] + 1) / 2.0
    score = max(0, min(1, score))

    if debug:
        print(f"    score={score:.2f} moves={move_count} api_calls={api_calls}")

    if score >= 0.5 and len(messages) >= 3:
        task_id = config["idx"] * 100_000_000 + random.randint(0, 99_999_999)
        return {
            "messages": messages,
            "env": "GAME",
            "source": "distillation",
            "distill_model": MODEL,
            "game": game_name,
            "score": score,
            "task_id": task_id,
            "seed": seed,
        }, api_calls

    return None, api_calls


def main():
    parser = argparse.ArgumentParser(description="GAME LLM distillation")
    parser.add_argument("--games", help="Comma-separated game names")
    parser.add_argument("--all", action="store_true", help="All 7 active games")
    parser.add_argument("-n", "--count", type=int, default=50, help="Seeds per game")
    parser.add_argument("-o", "--output", default="data/game_distill.jsonl")
    parser.add_argument("--start-seed", type=int, default=2000000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    if args.all:
        games = list(ACTIVE_GAMES.keys())
    elif args.games:
        games = [g.strip() for g in args.games.split(",")]
    else:
        # Default: focus on underrepresented games
        games = ["othello", "hex", "clobber", "liars_dice"]

    os.chdir(OPENSPIEL_DIR)
    output_path = os.path.join(PROJECT_DIR, args.output)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    print(f"GAME LLM Distillation")
    print(f"  Games: {', '.join(games)}")
    print(f"  Seeds/game: {args.count}")
    print(f"  Model: {MODEL}")
    print(f"  Output: {args.output}")
    print()

    total_api_calls = 0
    results = Counter()

    for game_name in games:
        if game_name not in ACTIVE_GAMES:
            print(f"  SKIP {game_name} (not in active games)")
            continue

        print(f"  {game_name}: ", end="", flush=True)
        wins = 0
        losses = 0

        for i in range(args.count):
            seed = args.start_seed + i
            try:
                record, api_calls = play_game(game_name, seed, debug=args.debug)
                total_api_calls += api_calls
                if record:
                    with open(output_path, "a") as f:
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    wins += 1
                else:
                    losses += 1
            except Exception as e:
                losses += 1
                if args.debug:
                    print(f"\n    seed={seed} error: {e}")
                elif i < 2:
                    print(f"err({e.__class__.__name__}) ", end="", flush=True)

        rate = wins * 100 // max(wins + losses, 1)
        print(f"{wins}/{wins+losses} wins ({rate}%)")
        results[game_name] = wins

    print(f"\nTotal: {sum(results.values())} entries, {total_api_calls} API calls")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
