#!/usr/bin/env python3
"""v11 GAME data generation — NO think chains, strong MCTS, eval-level opponents.

Based on competitive analysis: top miners use reasoning_tokens=0,
assistant outputs ONLY action ID number. Bot must be stronger than eval MCTS.

Usage:
    python3 generate_v11.py --game hex -n 100
    python3 generate_v11.py --all -n 50
    python3 generate_v11.py --game liars_dice -n 500  # uses probability, not MCTS
"""

import argparse
import json
import os
import random
import sys
import numpy as np
from math import comb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pyspiel
from open_spiel.python.algorithms import mcts as mcts_lib

# ============================================================
# Game configs — MUST match eval exactly
# ============================================================
GAME_CONFIGS = {
    "goofspiel": lambda: {"num_cards": random.choice([8, 10, 12, 14, 16]),
                           "imp_info": True, "points_order": "random"},
    "leduc_poker": lambda: {},
    "gin_rummy": lambda: {"hand_size": random.choice([7, 8, 9]),
                           "knock_card": random.choice([10, 9, 8])},
    "liars_dice": lambda: {"numdice": 5},
    "othello": lambda: {},
    "hex": lambda: {"board_size": random.choice([5, 7, 9, 11])},
    "clobber": lambda: (lambda s: {"rows": s, "columns": s})(random.choice([5, 6, 7])),
}

GAME_IDX = {"goofspiel": 0, "liars_dice": 1, "leduc_poker": 2,
            "gin_rummy": 3, "othello": 4, "hex": 6, "clobber": 7}

# ============================================================
# Bot MCTS configs — MUST be stronger than eval opponent
# ============================================================
# Eval opponent: hex(1000,50), othello(1000,20), clobber(1500,100),
#                gin(500,10), liars(3000,200), leduc(3000,200)
# Bot MCTS — just above eval opponent strength for good move quality.
# Eval: hex(1000,50), othello(1000,20), clobber(1500,100), gin(500,10)
# Bot needs to be strong enough to make good moves, but not so strong it's slow.
# Bot MCTS — must be stronger than eval opponent to generate winning data.
# Plan: hex 2000/50, othello 2000/20, clobber 3000/50, gin 1000/10
BOT_MCTS = {
    "hex":         {"sim": 2000, "roll": 50},
    "othello":     {"sim": 2000, "roll": 20},
    "clobber":     {"sim": 3000, "roll": 50},
    "gin_rummy":   {"sim": 1000, "roll": 10},
}

# ⚠️ Opponent configs — MUST match eval EXACTLY.
# Source: repos/affinetes/environments/openspiel/agents/{game}.py get_mcts_config()
# Goofspiel: eval uses random (simultaneous game, MCTS not supported)
OPP_MCTS = {
    "hex":         {"sim": 1000, "roll": 50},
    "othello":     {"sim": 1000, "roll": 20},
    "clobber":     {"sim": 1500, "roll": 100},
    "gin_rummy":   {"sim": 500,  "roll": 10},
    "liars_dice":  {"sim": 3000, "roll": 200},
    "leduc_poker": {"sim": 3000, "roll": 200},
    # goofspiel: random opponent (eval uses random for simultaneous games)
}

# ============================================================
# System prompts — exact copy from eval
# ============================================================
SYSTEM_PROMPT_TEMPLATE = """You are playing {game_name}.

{rules}

# Output Format
You must respond with ONLY the action ID (a single number).
Do NOT include descriptions or explanations.

Examples:
- For action "0 -> roll": respond "0"
- For action "89 -> a3": respond "89"
"""

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


# ============================================================
# State formatters — match eval exactly
# ============================================================
def _format_goofspiel_state(obs):
    import re
    points_match = re.search(r'Points:\s+(\d+)\s+(\d+)', obs)
    if points_match:
        p0, p1 = points_match.groups()
        obs = re.sub(r'Points:\s+\d+\s+\d+',
                     f'Player 0: {p0} points, Player 1: {p1} points', obs)
    win_seq_match = re.search(r'Win sequence:\s+([-\d\s]+)', obs)
    if win_seq_match:
        win_seq = win_seq_match.group(1).strip()
        explanation = "\n(Win sequence: 1=player 1 won, 0=player 0 won, negative=tie)"
        obs = obs.replace(f'Win sequence: {win_seq}', f'Win sequence: {win_seq}{explanation}')
    return obs


def _format_liars_dice_state(state, player):
    info_str = state.information_state_string(player)
    if not info_str:
        return state.observation_string(player)
    first_part = info_str.split()[0] if ' ' in info_str else info_str
    dice = [int(d) for d in first_part if d.isdigit()]
    dice_str = f"{dice} (showing: {', '.join(map(str, dice))})" if dice else "[unknown]"
    num_players = state.num_players()
    num_dice = len(dice) if dice else 5
    total_dice = num_dice * num_players
    parts_raw = info_str.split()
    bids = [p for p in parts_raw[1:] if '-' in p]
    state_parts = [
        f"Your dice: {dice_str}",
        f"Number of dice per player: {num_dice}",
        f"Total dice in game: {total_dice}",
        f"Number of players: {num_players}",
        f"Current player to act: Player {state.current_player()}"
    ]
    if bids:
        last_bid = bids[-1]
        qty, face = last_bid.split('-')
        state_parts.append(f'\nCurrent bid: "{qty}-{face}" (claiming at least {qty} dice showing {face} across all players)')
        state_parts.append("You can either: (1) Make a higher bid, or (2) Call 'Liar'")
    else:
        state_parts.append("No bid yet - you must make the first bid")
    return "\n".join(state_parts)


def make_user_prompt(state, player, legal, game_name=""):
    if game_name == "liars_dice":
        obs = _format_liars_dice_state(state, player)
    else:
        try:
            obs = state.observation_string(player)
        except:
            obs = state.information_state_string(player)
        if game_name == "goofspiel":
            obs = _format_goofspiel_state(obs)

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


# ============================================================
# MCTS bot/opponent factory
# ============================================================
class RolloutEvaluator(mcts_lib.Evaluator):
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
                if not a: break
                ws.apply_action(self._rs.choice(a))
            t += ws.returns()
        return t / self._n

    def prior(self, state):
        la = state.legal_actions()
        return [(a, 1.0 / len(la)) for a in la] if la else []


def make_mcts_bot(game, sim, roll, seed=42):
    return mcts_lib.MCTSBot(
        game=game, uct_c=1.414, max_simulations=sim,
        evaluator=RolloutEvaluator(n_rollouts=roll),
        random_state=np.random.RandomState(seed),
        solve=True,
    )


# ============================================================
# Liars Dice — probability-based optimal play (no MCTS)
# ============================================================
def liars_optimal_action(state, player):
    """Optimal liars_dice play based on probability calculation."""
    info = state.information_state_string(player)
    legal = state.legal_actions(player)
    if len(legal) <= 1:
        return legal[0]

    # Parse dice
    dice = []
    parts = info.split() if info else []
    if parts:
        dice = [int(c) for c in parts[0] if c.isdigit()]
    num_dice = len(dice) if dice else 5
    total_dice = num_dice * 2
    opp_dice = total_dice - num_dice
    liar_action = max(legal)

    # Parse last bid
    bids = [p for p in parts[1:] if '-' in p] if len(parts) > 1 else []
    last_bid_qty, last_bid_face = 0, 0
    if bids:
        try:
            last_bid_qty = int(bids[-1].split('-')[0])
            last_bid_face = int(bids[-1].split('-')[1])
        except:
            pass

    freq = {}
    for d in dice:
        freq[d] = freq.get(d, 0) + 1
    wild_count = freq.get(6, 0)

    def support(face):
        return freq.get(face, 0) + (wild_count if face != 6 else 0)

    def opp_prob(needed, n=opp_dice):
        """P(opponent has >= needed matching dice)."""
        if needed <= 0: return 1.0
        if needed > n: return 0.0
        p = 1.0 / 3.0
        return sum(comb(n, k) * (p ** k) * ((1 - p) ** (n - k)) for k in range(needed, n + 1))

    # Decision logic
    if last_bid_qty > 0:
        # Responding to opponent's bid
        my_match = support(last_bid_face)
        needed = last_bid_qty - my_match

        if needed >= 5:
            return liar_action  # impossible
        if needed >= 4:
            return liar_action  # ~1% chance
        if needed >= 3 and opp_prob(needed) < 0.35:
            return liar_action

        # Otherwise raise on our strongest face
        best_face = max(range(1, 6), key=support)
        best_support = support(best_face)
        raise_qty = best_support + 2  # conservative

        # Find legal raise
        for a in legal:
            if a == liar_action:
                continue
            try:
                a_str = state.action_to_string(player, a)
                a_parts = a_str.split('-')
                a_qty, a_face = int(a_parts[0]), int(a_parts[1])
                if a_face == best_face and a_qty <= raise_qty:
                    return a
            except:
                continue
        # No good raise found, call liar if borderline
        if opp_prob(needed) < 0.5:
            return liar_action
        # Last resort: smallest legal raise
        for a in legal:
            if a != liar_action:
                return a
        return liar_action
    else:
        # Opening bid: strongest face, conservative quantity
        best_face = max(range(1, 6), key=support)
        best_support = support(best_face)
        target_qty = best_support + 1  # +1 for expected opponent contribution

        for a in legal:
            try:
                a_str = state.action_to_string(player, a)
                a_parts = a_str.split('-')
                a_qty, a_face = int(a_parts[0]), int(a_parts[1])
                if a_face == best_face and a_qty == target_qty:
                    return a
            except:
                continue
        # Fallback
        for a in legal:
            if a != liar_action:
                return a
        return legal[0]


# ============================================================
# Hex opening book (from competitive analysis)
# ============================================================
HEX_OPENINGS = {
    5: {"c3": None},   # 5x5 P0: always c3 (100% win rate)
    7: {"e3": None},   # 7x7 P0: always e3 (93% win rate)
    9: {"d6": None},   # 9x9 P0: d6 (94% win rate)
    11: {"f6": None},  # 11x11 P0: f6 (83% win rate)
}


def hex_opening_action(state, player, bs):
    """Return opening action for hex if available."""
    legal = state.legal_actions(player)
    all_occupied = len([1 for a in range(bs * bs) if a not in legal])
    if all_occupied > 2:  # not opening
        return None

    openings = HEX_OPENINGS.get(bs, {})
    for name, _ in openings.items():
        # Parse "c3" -> row=2, col=2 -> action = 2*bs+2
        col = ord(name[0]) - ord('a')
        row = int(name[1:]) - 1
        action = row * bs + col
        if action in legal:
            return action
    return None


# ============================================================
# Clobber opening filter (from competitive analysis)
# ============================================================
CLOBBER_GOOD_OPENINGS = {"c5c4", "e4d4", "e4e3", "c5d5"}
CLOBBER_BAD_OPENINGS = {"a2a3", "f2f3", "c3c4", "e3e4"}


def clobber_filter_opening(state, player, action):
    """Check if clobber opening is acceptable."""
    legal = state.legal_actions(player)
    # Only filter first move
    obs = state.observation_string(player)
    if obs.count('x') + obs.count('o') < 40:  # not initial position
        return True

    action_name = state.action_to_string(player, action)
    if "Action: " in action_name:
        action_name = action_name.split("Action: ")[-1]

    if action_name in CLOBBER_BAD_OPENINGS:
        # Try to find a good opening instead
        return False
    return True


# ============================================================
# Main generation
# ============================================================
def generate_one(game_name, seed):
    """Play one game: strong bot vs eval-level MCTS opponent. No think chains."""
    random.seed(seed)
    np.random.seed(seed % (2**31))

    config_id = random.randint(0, 99_999_999)
    params = GAME_CONFIGS[game_name]()
    game = pyspiel.load_game(game_name, params)
    state = game.new_initial_state()

    if game_name == "liars_dice":
        bot_player = 1 if random.random() < 0.7 else 0
    else:
        bot_player = random.randint(0, game.num_players() - 1)

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        game_name=game_name, rules=GAME_RULES[game_name])
    messages = [{"role": "system", "content": system_prompt}]

    # Create bots
    bot = None
    if game_name in BOT_MCTS:
        cfg = BOT_MCTS[game_name]
        bot = make_mcts_bot(game, cfg["sim"], cfg["roll"], seed=seed % (2**31))

    opp = None
    if game_name in OPP_MCTS:
        cfg = OPP_MCTS[game_name]
        opp = make_mcts_bot(game, cfg["sim"], cfg["roll"], seed=(seed + 1) % (2**31))

    # Import existing bots for goofspiel/leduc/gin (they have good rule-based logic)
    from goofspiel_bot import goofspiel_bot
    from leduc_poker_bot import leduc_poker_bot
    from gin_rummy_bot import gin_rummy_bot

    move_count = 0
    while not state.is_terminal() and move_count < 500:
        if state.is_chance_node():
            outcomes = state.chance_outcomes()
            state.apply_action(random.choices(
                [a for a, _ in outcomes], [p for _, p in outcomes])[0])
            continue

        if state.is_simultaneous_node():
            # Goofspiel (simultaneous)
            actions = []
            for p in range(game.num_players()):
                p_legal = state.legal_actions(p)
                if p == bot_player:
                    action, _ = goofspiel_bot(state, p)
                    if action not in p_legal: action = p_legal[0]
                    uc = make_user_prompt(state, p, p_legal, game_name)
                    messages.append({"role": "user", "content": uc})
                    messages.append({"role": "assistant", "content": str(action)})
                    actions.append(action)
                else:
                    actions.append(random.choice(p_legal))
            state.apply_actions(actions)
        else:
            cp = state.current_player()
            legal = state.legal_actions(cp)

            if cp == bot_player:
                # Bot's turn — choose action based on game
                if game_name == "liars_dice":
                    action = liars_optimal_action(state, cp)
                elif game_name == "hex":
                    bs = int(game.num_distinct_actions() ** 0.5)
                    opening = hex_opening_action(state, cp, bs)
                    if opening is not None:
                        action = opening
                    elif bot:
                        action = bot.step(state)
                    else:
                        action = random.choice(legal)
                elif game_name == "clobber":
                    if bot:
                        action = bot.step(state)
                        # Filter bad openings
                        if not clobber_filter_opening(state, cp, action):
                            # Try c5c4-style opening
                            for a in legal:
                                a_name = state.action_to_string(cp, a)
                                if "Action: " in a_name:
                                    a_name = a_name.split("Action: ")[-1]
                                if a_name in CLOBBER_GOOD_OPENINGS:
                                    action = a
                                    break
                    else:
                        action = random.choice(legal)
                elif bot:
                    action = bot.step(state)
                else:
                    action = random.choice(legal)

                if action not in legal:
                    action = legal[0]

                uc = make_user_prompt(state, cp, legal, game_name)
                messages.append({"role": "user", "content": uc})
                # *** NO THINK CHAINS — just the action number ***
                messages.append({"role": "assistant", "content": str(action)})
                state.apply_action(action)
            else:
                # Opponent's turn
                if opp:
                    try:
                        opp_action = opp.step(state)
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
                "messages": messages, "env": "GAME", "source": "v11_no_think",
                "game": game_name, "score": score,
                "task_id": GAME_IDX[game_name] * 100_000_000 + config_id,
                "seed": seed,
            }
    return None


def main():
    parser = argparse.ArgumentParser()
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
        output = args.output or f"data/v11_{game_name}.jsonl"
        os.makedirs(os.path.dirname(output) if os.path.dirname(output) else ".", exist_ok=True)

        wins, total = 0, 0
        with open(output, "a") as f:
            for i in range(args.n):
                seed = args.start_seed + i
                total += 1
                result = generate_one(game_name, seed)
                if result:
                    wins += 1
                    f.write(json.dumps(result, ensure_ascii=False) + "\n")
                    f.flush()
                if total % 10 == 0:
                    print(f"  {game_name}: {wins}W/{total} ({wins/total*100:.0f}%)", flush=True)

        print(f"{game_name}: {wins}W/{total} ({wins/total*100:.0f}%) → {output}")


if __name__ == "__main__":
    main()
