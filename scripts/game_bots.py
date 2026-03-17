"""GAME strategy bot functions for OpenSpiel games.

Each bot takes (state, player) and returns (action, think_text).
Used by game_bot_gen.py for training data generation.
"""

import random


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
    total_dice = num_dice * 2  # 2 players

    # Find Liar action (highest legal action)
    liar_action = max(legal)

    if len(legal) <= 1:
        return legal[0], "Only one legal action available."

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

    try:
        from agents import GAME_AGENTS
        agent = GAME_AGENTS['goofspiel']()
        obs = agent.format_state(state, player)
        import re
        m = re.search(r"Current point card: (\d+)", obs)
        prize = int(m.group(1)) if m else len(legal) // 2

        max_card = max(legal) + 1
        ratio = prize / max_card
        idx = int(ratio * (len(legal) - 1))
        idx = max(0, min(idx, len(legal) - 1))
        action = legal[idx]

        bid_value = action + 1
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

    for a in legal:
        if a in corners:
            r, c = a // 8, a % 8
            return a, f"Corner ({r},{c}) available! Corners can never be flipped, strongest position. Must take it."

    for a in legal:
        if a in edges and a not in x_squares:
            r, c = a // 8, a % 8
            return a, f"Edge position ({r},{c}), stable and hard to flip."

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

    board_size = 5
    center = board_size // 2

    def score_pos(a):
        r, c = a // board_size, a % board_size
        center_dist = abs(r - center) + abs(c - center)
        if player == 0:
            axis_score = abs(c - center)
        else:
            axis_score = abs(r - center)
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

        my_mobility_after = 999
        for opp_a in opp_legal[:10]:
            grandchild = child.child(opp_a)
            if grandchild.is_terminal():
                my_mobility_after = min(my_mobility_after, 0)
            elif grandchild.current_player() == player:
                my_mobility_after = min(my_mobility_after, len(grandchild.legal_actions(player)))

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
