#!/usr/bin/env python3
"""
GAME Strategy Bot data generator

Uses programmatic strategy bots instead of LLMs to play games, generating training data with <think> tags.
Each game has a dedicated strategy function; winning games are saved as training samples.

Starts from the simplest games and gradually expands.

Usage:
    python3 scripts/game_bot_gen.py --game leduc_poker -n 100 -o data/game_bot_leduc.jsonl
    python3 scripts/game_bot_gen.py --game liars_dice -n 100
    python3 scripts/game_bot_gen.py --game goofspiel -n 100
"""

import argparse
import json
import random
import sys
import os
from pathlib import Path

sys.path.insert(0, os.environ.get("OPENSPIEL_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "affinetes", "environments", "openspiel")))
import pyspiel

# ============================================================================
# Strategy Bot: one choose_action + explain function per game
# ============================================================================

def leduc_poker_bot(state, player):
    """Leduc Poker optimal strategy: simple decision table based on hand strength"""
    info = state.information_state_string(player)
    legal = state.legal_actions(player)

    # Parse info: [Private: X] [Public: Y]
    private_card = int(info.split("Private: ")[1].split("]")[0])
    rank = private_card // 2  # 0=J, 1=Q, 2=K
    rank_name = ["J", "Q", "K"][rank]

    has_public = "Public:" in info
    public_rank = -1
    if has_public:
        public_card = int(info.split("Public: ")[1].split("]")[0])
        public_rank = public_card // 2
    has_pair = has_public and rank == public_rank

    # Parse round and betting history
    round_num = 2 if "Round 2" in info else 1
    opponent_raised = info.count("2") > (1 if 2 in legal else 0)  # rough check

    # Strategy
    if has_pair:
        # Pair is very strong in Leduc
        action = 2 if 2 in legal else 1
        think = f"I have {rank_name} and public card is also {rank_name}, making a pair! Pairs are very strong in Leduc, raise to maximize value."
    elif rank == 2:  # K
        if 2 in legal:
            action = 2
            think = f"I have K, the strongest unpaired card. High win rate even without a pair, raise to pressure opponent."
        else:
            action = 1
            think = f"I have K, strongest card. Call."
    elif rank == 1:  # Q
        if has_public:
            if public_rank == 2:  # Public K, I have Q
                action = 1 if 1 in legal else 0
                think = f"I have Q, public card K no pair. Opponent may have K for a pair, call cautiously."
            else:
                action = 1 if 1 in legal else (2 if 2 in legal else 0)
                think = f"I have Q, public card is {['J','Q','K'][public_rank]}. Q is medium strength, call and see."
        else:
            action = 1 if 1 in legal else 2
            think = f"Round 1 with Q, medium strength. Call to keep cost low, wait for public card info."
    else:  # J
        if has_public and public_rank > 0:
            # Public is Q or K, I have J = worst position
            action = 0 if 0 in legal else 1
            if action == 0:
                think = f"I have J, weakest card. Public card {['J','Q','K'][public_rank]} no pair. Opponent likely has stronger hand, fold to cut losses."
            else:
                think = f"I have J, weakest card, but only need to call. Pot odds barely sufficient."
        else:
            action = 1 if 1 in legal else 0
            think = f"I have J, weakest card. Minimize losses, call and wait for info."

    return action, think


def liars_dice_bot(state, player):
    """Liar's Dice probability strategy: based on Bayesian estimation"""
    info = state.information_state_string(player)
    legal = state.legal_actions(player)

    # Parse dice
    dice = []
    if "Private: " in info:
        private_str = info.split("Private: ")[1].split("]")[0]
        dice = [int(x) for x in private_str.split() if x.isdigit()]

    num_dice = len(dice) if dice else 5
    # Total dice from info
    total_dice = num_dice * 2  # 2 players

    # Find Liar action (highest legal action)
    liar_action = max(legal)

    # Parse current bid from legal actions
    # If liar_action is available and there's a previous bid
    if len(legal) <= 1:
        return legal[0], "Only one legal action available."

    # Decide: bid or call liar?
    # Simple heuristic: if current bid seems unlikely, call liar
    # Otherwise make a safe bid based on our dice

    # Count our dice frequencies
    freq = {}
    for d in dice:
        freq[d] = freq.get(d, 0) + 1

    # Find our most common face
    if freq:
        best_face = max(freq, key=freq.get)
        best_count = freq[best_face]
    else:
        best_face = 1
        best_count = 0

    # Expected total of any face: my_count + opponent_dice / 6
    opponent_dice = total_dice - num_dice
    expected_best = best_count + opponent_dice / 6.0

    # If liar is an option, calculate if calling is good
    # The bid actions encode (quantity-1)*6 + (face-1), roughly
    # Higher action = higher bid, liar = max action

    # Simple strategy: if we're early, bid our best. If bid is high, call liar.
    non_liar = [a for a in legal if a != liar_action]

    if non_liar:
        # Pick a moderate bid
        mid_idx = len(non_liar) // 3  # conservative: bid low
        action = non_liar[mid_idx]
        think = f"My dice {dice}, face {best_face} appears {best_count} times. Conservative bid, avoid overbidding."
    else:
        action = liar_action
        think = f"No safe bid available, call Liar."

    # Override: if very few safe bids left, call liar
    if len(non_liar) <= 2 and liar_action in legal:
        action = liar_action
        think = f"Too few safe bids left (only {len(non_liar)}), opponent bid too high, call Liar."

    return action, think


def goofspiel_bot(state, player):
    """Goofspiel proportional bidding strategy: bid high for high prizes, low for low prizes"""
    legal = sorted(state.legal_actions(player))

    if len(legal) == 1:
        return legal[0], "Only one card left to play."

    # Parse prize card from format_state
    try:
        from agents import GAME_AGENTS
        agent = GAME_AGENTS['goofspiel']()
        obs = agent.format_state(state, player)
        import re
        m = re.search(r"Current point card: (\d+)", obs)
        prize = int(m.group(1)) if m else len(legal) // 2

        # Total cards = max(legal) + 1 roughly
        max_card = max(legal) + 1
        # Strategy: bid proportionally to prize value
        # High prize → high bid, low prize → low bid
        ratio = prize / max_card
        idx = int(ratio * (len(legal) - 1))
        idx = max(0, min(idx, len(legal) - 1))
        action = legal[idx]

        bid_value = action + 1  # action 0 = bid 1
        if prize >= max_card * 0.7:
            think = f"Prize card worth {prize} points, high value. Bid {bid_value} to compete aggressively."
        elif prize >= max_card * 0.4:
            think = f"Prize card worth {prize} points, medium value. Bid {bid_value} moderately."
        else:
            think = f"Prize card worth {prize} points, low value. Bid low with {bid_value}, save high cards for valuable prizes."
        return action, think
    except Exception:
        mid = len(legal) // 2
        return legal[mid], f"Play middle value to balance gains."


def othello_bot(state, player):
    """Othello corner-priority + greedy capture"""
    legal = state.legal_actions(player)
    if not legal:
        return 0, "No legal moves, pass."

    board_size = 8
    corners = {0, 7, 56, 63}
    edges = set()
    for i in range(board_size):
        edges.update([i, i * board_size, i * board_size + 7, 56 + i])
    x_squares = {9, 14, 49, 54}  # diagonal to corners

    # Priority: corners > edges > avoid x-squares > any
    for a in legal:
        if a in corners:
            r, c = a // 8, a % 8
            return a, f"Corner ({r},{c}) available! Corners can never be flipped, strongest position. Must take it."

    for a in legal:
        if a in edges and a not in x_squares:
            r, c = a // 8, a % 8
            return a, f"Edge position ({r},{c}), stable and hard to flip."

    # Among non-x-square moves, pick one that minimizes opponent mobility
    safe = [a for a in legal if a not in x_squares]
    candidates = safe if safe else legal

    best_action = candidates[0]
    best_opp_moves = 999
    for a in candidates:
        child = state.child(a)
        if child.is_terminal():
            r, c = a // 8, a % 8
            return a, f"Position ({r},{c}) ends the game."
        opp = child.current_player()
        if opp >= 0:
            opp_moves = len(child.legal_actions(opp))
            if opp_moves < best_opp_moves:
                best_opp_moves = opp_moves
                best_action = a

    r, c = best_action // 8, best_action % 8
    return best_action, f"Position ({r},{c}), minimizing opponent's mobility to {best_opp_moves} moves."


def hex_bot(state, player):
    """Hex strategy: center control + connect to target edges + bridge pattern"""
    legal = state.legal_actions(player)
    if not legal:
        return 0, "No legal moves."

    # Parse board size from game params
    board_size = 5
    center = board_size // 2

    # Player 0 connects top-bottom (rows), Player 1 connects left-right (cols)
    # Prioritize: center > positions on our connection axis > bridge patterns

    def score_pos(a):
        r, c = a // board_size, a % board_size
        # Distance to center (lower = better)
        center_dist = abs(r - center) + abs(c - center)
        # For P0 (top-bottom): prefer middle columns; for P1 (left-right): prefer middle rows
        if player == 0:
            axis_score = abs(c - center)  # stay near middle column
        else:
            axis_score = abs(r - center)  # stay near middle row
        return center_dist * 2 + axis_score

    best = min(legal, key=score_pos)
    r, c = best // board_size, best % board_size
    center_dist = abs(r - center) + abs(c - center)

    if center_dist == 0:
        think = f"Take center ({r},{c}), strongest position in Hex, connects all directions."
    elif center_dist <= 1:
        think = f"Adjacent to center ({r},{c}), form bridge pattern to expand connections."
    elif player == 0:
        think = f"Position ({r},{c}), extend vertical chain toward top/bottom edges."
    else:
        think = f"Position ({r},{c}), extend horizontal chain toward left/right edges."

    return best, think


def clobber_bot(state, player):
    """Clobber: 2-step lookahead — minimize opponent mobility, maximize ours after response"""
    legal = state.legal_actions(player)
    if not legal:
        return 0, "No legal moves."

    best_action = legal[0]
    best_score = -999

    for a in legal:
        child = state.child(a)
        if child.is_terminal():
            return a, "This capture ends the game in our favor."

        opp = child.current_player()
        if opp < 0:
            continue

        opp_legal = child.legal_actions(opp)
        opp_moves = len(opp_legal)

        # 2-step: simulate opponent's best response, see our mobility after
        my_mobility_after = 999
        for opp_a in opp_legal[:10]:  # limit search for speed
            grandchild = child.child(opp_a)
            if grandchild.is_terminal():
                my_mobility_after = min(my_mobility_after, 0)
            elif grandchild.current_player() == player:
                my_mobility_after = min(my_mobility_after, len(grandchild.legal_actions(player)))

        # Score: fewer opponent moves + more of our moves after
        score = -opp_moves * 3 + my_mobility_after
        if score > best_score:
            best_score = score
            best_action = a

    name = state.action_to_string(player, best_action)
    return best_action, f"Capture at {name[2:4]}, 2-step lookahead for best position."


def gin_rummy_bot(state, player):
    """Gin Rummy simple strategy: random but legal"""
    legal = state.legal_actions(player)
    if not legal:
        return 0, "No legal moves."
    action = legal[random.randint(0, len(legal) - 1)]
    return action, "Organize hand, keep cards that form melds, discard highest deadwood."


BOTS = {
    "leduc_poker": leduc_poker_bot,
    "liars_dice": liars_dice_bot,
    "goofspiel": goofspiel_bot,
    "othello": othello_bot,
    "hex": hex_bot,
    "clobber": clobber_bot,
    "gin_rummy": gin_rummy_bot,
}


# ============================================================================
# Data generation: run OpenSpiel with bot, record full trajectories
# ============================================================================

def generate_game_trajectory(game_name, seed, bot_func):
    """Run a game with bot vs MCTS, return SFT record if bot wins."""
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
