#!/usr/bin/env python3
"""Generate data with rule-think bots. Standalone — no affinetes dependency.

Usage:
    python3 generate_rule_think.py --game othello -n 50
    python3 generate_rule_think.py --all -n 100
    python3 generate_rule_think.py --game liars_dice -n 200 --vs-mcts
"""

import argparse
import json
import os
import random
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["GAME_GEN_MODE"] = "1"

import pyspiel

# Import original MCTS bots (with enhanced game_context)
from goofspiel_bot import goofspiel_bot
from leduc_poker_bot import leduc_poker_bot
from gin_rummy_bot import gin_rummy_bot
from liars_dice_bot import liars_dice_bot
from othello_bot import othello_bot
from hex_bot import hex_bot
from clobber_bot import clobber_bot

BOTS = {
    "goofspiel": goofspiel_bot,
    "leduc_poker": leduc_poker_bot,
    "gin_rummy": gin_rummy_bot,
    "liars_dice": liars_dice_bot,
    "othello": othello_bot,
    "hex": hex_bot,
    "clobber": clobber_bot,
}

# Game configs matching eval
GAME_CONFIGS = {
    "goofspiel": lambda cid: {"num_cards": random.choice([4, 5, 6, 7, 8, 9, 10, 11, 12, 13]),
                               "imp_info": True, "points_order": "descending"},
    "leduc_poker": lambda cid: {},
    "gin_rummy": lambda cid: {},
    "liars_dice": lambda cid: {"numdice": random.choice([1, 2, 3, 4, 5])},
    "othello": lambda cid: {},
    "hex": lambda cid: {"board_size": random.choice([5, 7, 9, 11])},
    "clobber": lambda cid: {"rows": random.choice([4, 5, 6]),
                             "columns": random.choice([4, 5, 6])},
}

GAME_IDX = {"goofspiel": 0, "liars_dice": 1, "leduc_poker": 2,
            "gin_rummy": 3, "othello": 4, "hex": 6, "clobber": 7}

# Eval-aligned system prompt
SYSTEM_PROMPT_TEMPLATE = """You are playing {game_name}.

{rules}

# Output Format
You must respond with ONLY the action ID (a single number).
Do NOT include descriptions or explanations.

Examples:
- For action "0 -> roll": respond "0"
- For action "89 -> a3": respond "89"
"""

# EXACT eval rules from repos/affinetes/environments/openspiel/agents/*.py
# ⚠️ DO NOT MODIFY — must match eval system prompt EXACTLY to avoid distribution shift
# Source of truth: repos/affinetes/environments/openspiel/agents/{game}.py get_rules()
# Any change here WILL cause training-eval mismatch and score regression
GAME_RULES = {
    "goofspiel": """GOOFSPIEL RULES:
Setup: Each player has bid cards numbered 1 to N. A prize deck with cards 1 to N is shuffled.
Goal: Win the most points by bidding on prize cards.

Each turn:
1. Reveal top prize card (worth its face value in points)
2. Players simultaneously play one bid card from their hand
3. Highest bidder wins the prize card (adds its value to score)
4. If bids tie, prize card is discarded (no one gets points)

Winning: Player with most points after all rounds wins.""",

    "leduc_poker": """LEDUC POKER RULES:

Deck: 2 suits × (num_players + 1) ranks. For 2 players: 6 cards (J♠ J♥ Q♠ Q♥ K♠ K♥).

Setup: Each player starts with 100 chips, pays 1 ante. Two rounds of betting.

Round 1: Each player receives one private card. Actions: Fold (lose ante), Call/Check (match current bet), Raise (add 2 chips to bet). Maximum 2 raises per round.
Round 2: One public card is revealed. Same actions, but Raise adds 4 chips.

Winning: Player with best hand wins pot (or last remaining if others fold).
Hand ranking (high to low): Pair (private + public match) > High card value (K > Q > J).""",

    "gin_rummy": """GIN RUMMY RULES:

SETUP:
- 52-card deck, each player receives 7-10 cards (variant dependent)
- Goal: Form MELDS to minimize DEADWOOD (unmelded cards)

MELDS (Valid Combinations):
1. SET: 3+ cards of SAME RANK (e.g., 7♠ 7♥ 7♣)
2. RUN: 3+ CONSECUTIVE cards of SAME SUIT (e.g., 5♦ 6♦ 7♦)

CARD NOTATION:
- Ranks: A(Ace), 2-9, T(10), J(Jack), Q(Queen), K(King)
- Suits: s(spades), h(hearts), d(diamonds), c(clubs)

EACH TURN:
1. DRAW phase: Pick from stock pile (53) OR discard pile upcard (52)
2. DISCARD phase: Choose ONE card from hand to discard

KNOCKING: When deadwood ≤ knock_card value, you may knock (action 55) to end the hand.""",

    "liars_dice": """LIAR'S DICE RULES:

Setup: Each player has N dice (1-5 depending on variant). All players roll their dice secretly.

Goal: Make bids about total dice across ALL players, or call "Liar" on opponent's bid.

Actions:
- Bid (quantity, face): Claim there are at least 'quantity' dice showing 'face' among all dice.
- Call Liar: Challenge the previous bid.

Bidding rules: Each bid must be higher than the previous bid. "Higher" means:
  - Same face value but higher quantity (e.g., "2 fours" beats "1 four")
  - Same quantity but higher face value (e.g., "2 fives" beats "2 fours")

Wild dice: 6s are WILD and count as ANY face value.
- When counting dice for a bid, include 6s in the count
- Example: Bid "3 fours" means at least 3 dice showing EITHER 4 OR 6

Winning: If you call Liar and previous bid was false, opponent loses. If bid was true or exact, you lose.""",

    "othello": """OTHELLO (REVERSI) RULES:
Board: 8×8 grid. 2 players (Black and White). Start with 4 discs in center (2 black, 2 white diagonal).
Goal: Have more discs of your color when board is full or no moves available.

Turn: Place disc to sandwich opponent's discs between your new disc and existing disc (horizontally, vertically, or diagonally). All sandwiched opponent discs flip to your color.
Must flip at least 1 disc; if no valid move, pass turn.

Winning: Player with most discs when game ends wins.""",

    "hex": """HEX RULES:
Board: Diamond-shaped grid (5×5, 7×7, 9×9, or 11×11). Two players (Red and Blue).
Goal: Connect your two opposite sides of the board with an unbroken chain of your stones.

Turn: Place one stone of your color on any empty cell.
Red (x) connects top-left to bottom-right sides.
Blue (o) connects top-right to bottom-left sides.

No draws possible: Someone must win.""",

    "clobber": """CLOBBER RULES:
Board: Rectangular grid (5×5, 6×6, or 7×7) filled with alternating black and white pieces.
Goal: Be the last player able to move.

Movement: On your turn, move one of your pieces orthogonally (horizontally or vertically) to capture an adjacent opponent piece. The captured piece is removed and replaced by your piece.
Must capture: Every move must capture an opponent piece. No non-capturing moves allowed.

Important: You can ONLY move to a position occupied by an opponent piece that is directly adjacent (up/down/left/right) to one of your pieces.

Losing: If you have no legal moves (no adjacent opponent pieces to capture), you lose.""",
}


def make_user_prompt(state, player, legal):
    """Generate user prompt matching eval format."""
    try:
        obs = state.observation_string(player)
    except:
        try:
            obs = state.information_state_string(player)
        except:
            obs = str(state)

    actions_desc = []
    for a in legal:
        try:
            actions_desc.append(f"{a} -> {state.action_to_string(player, a)}")
        except:
            actions_desc.append(str(a))

    return (f"Current State:\n{obs}\n\n"
            f"You are Player {player}.\n"
            f"Legal Actions:\n" + "\n".join(actions_desc) + "\n\n"
            f"Your choice (ID only):")


def make_mcts_opponent(game, game_name, strength="full"):
    """Create MCTS opponent at specified strength.

    strength: "full" (eval-level), "medium" (300sim), "weak" (100sim)
    """
    try:
        from open_spiel.python.algorithms import mcts as mcts_lib

        class Evaluator(mcts_lib.Evaluator):
            def __init__(self, n_rollouts=5):
                self._n = n_rollouts
                self._rs = np.random.RandomState(123)
            def evaluate(self, state):
                if state.is_terminal(): return state.returns()
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

        # Strength levels
        if strength == "weak":
            sim, roll = 100, 3
        elif strength == "medium":
            sim, roll = 300, 5
        else:  # full
            from mcts_helper import CONFIGS
            cfg = CONFIGS.get(game_name, {})
            sim = cfg.get("gen_sim", 300)
            roll = cfg.get("gen_roll", 5)

        return mcts_lib.MCTSBot(
            game=game, uct_c=1.414, max_simulations=sim,
            evaluator=Evaluator(n_rollouts=roll),
            random_state=np.random.RandomState(456),
            solve=True,
        )
    except Exception as e:
        print(f"MCTS opponent failed: {e}")
        return None


def generate_one(game_name, seed, opp_mode="random"):
    """Play one game. opp_mode: 'random','weak','medium','full'."""
    random.seed(seed)
    np.random.seed(seed % (2**31))

    config_id = random.randint(0, 99_999_999)
    params = GAME_CONFIGS[game_name](config_id)
    game = pyspiel.load_game(game_name, params)
    state = game.new_initial_state()
    if game_name == "liars_dice":
        bot_player = 1 if random.random() < 0.7 else 0
    else:
        bot_player = random.randint(0, game.num_players() - 1)

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        game_name=game_name, rules=GAME_RULES[game_name])
    messages = [{"role": "system", "content": system_prompt}]
    bot_func = BOTS[game_name]
    vs_mcts = opp_mode != "random"

    # MCTS opponent
    mcts_opp = None
    if opp_mode in ("weak", "medium", "full"):
        mcts_opp = make_mcts_opponent(game, game_name, strength=opp_mode)

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
                    uc = make_user_prompt(state, p, p_legal)
                    messages.append({"role": "user", "content": uc})
                    messages.append({"role": "assistant",
                                     "content": f"<think>{think}</think>\n{action}"})
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
                uc = make_user_prompt(state, cp, legal)
                messages.append({"role": "user", "content": uc})
                messages.append({"role": "assistant",
                                 "content": f"<think>{think}</think>\n{action}"})
                state.apply_action(action)
            else:
                if mcts_opp and not state.is_chance_node():
                    try:
                        opp_action = mcts_opp.step(state)
                        if opp_action in legal:
                            state.apply_action(opp_action)
                        else:
                            state.apply_action(random.choice(legal))
                    except:
                        state.apply_action(random.choice(legal))
                else:
                    state.apply_action(random.choice(legal))
        move_count += 1

    if state.is_terminal() and len(messages) >= 3:
        returns = state.returns()
        score = max(0, min(1, (returns[bot_player] + 1) / 2.0))
        if score >= 0.5:
            return {
                "messages": messages, "env": "GAME", "source": "rule_think_bot",
                "game": game_name, "score": score,
                "task_id": GAME_IDX[game_name] * 100_000_000 + config_id,
                "seed": seed, "vs_mcts": vs_mcts, "opp_mode": opp_mode,
            }
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", choices=list(BOTS.keys()))
    parser.add_argument("--all", action="store_true")
    parser.add_argument("-n", default=50, type=int)
    parser.add_argument("-o", "--output", default=None)
    parser.add_argument("--start-seed", default=200000, type=int)
    parser.add_argument("--vs-mcts", action="store_true", help="Use full-strength MCTS opponent")
    parser.add_argument("--vs-weak-mcts", action="store_true", help="Use weak MCTS opponent (100sim, fast)")
    parser.add_argument("--vs-medium-mcts", action="store_true", help="Use medium MCTS opponent (300sim)")
    args = parser.parse_args()

    games = list(BOTS.keys()) if args.all else ([args.game] if args.game else [])
    if not games:
        parser.error("Specify --game or --all")

    # Determine opponent mode
    if args.vs_mcts:
        opp_mode = "full"
    elif args.vs_medium_mcts:
        opp_mode = "medium"
    elif args.vs_weak_mcts:
        opp_mode = "weak"
    else:
        opp_mode = "random"

    for game_name in games:
        output = args.output or f"data/rule_think_{game_name}.jsonl"
        os.makedirs(os.path.dirname(output) if os.path.dirname(output) else ".", exist_ok=True)

        wins, total = 0, 0
        for i in range(args.n):
            seed = args.start_seed + i
            total += 1
            try:
                record = generate_one(game_name, seed, opp_mode=opp_mode)
                if record:
                    with open(output, "a") as f:
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    wins += 1
            except Exception as e:
                if i < 3:
                    print(f"  {game_name} seed={seed}: {e}")

        rate = wins * 100 // max(total, 1)
        mode_label = {"full": "vs-MCTS-full", "medium": "vs-MCTS-medium",
                      "weak": "vs-MCTS-weak", "random": "vs-random"}[opp_mode]
        print(f"{game_name} ({mode_label}): {wins}W/{total} ({rate}%) → {output}")


if __name__ == "__main__":
    main()
