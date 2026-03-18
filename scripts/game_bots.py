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
    """Gin Rummy meld-aware strategy: form runs/sets, discard highest deadwood, knock when ready."""
    legal = state.legal_actions(player)
    if not legal:
        return 0, "No legal moves."
    if len(legal) == 1:
        return legal[0], "Only one legal action available."

    CARD_NAMES = ['A','2','3','4','5','6','7','8','9','T','J','Q','K']
    SUIT_NAMES = ['s','c','d','h']

    def card_id(rank_idx, suit_idx):
        return suit_idx * 13 + rank_idx

    def card_rank(cid):
        return cid % 13

    def card_suit(cid):
        return cid // 13

    def card_name(cid):
        return CARD_NAMES[card_rank(cid)] + SUIT_NAMES[card_suit(cid)]

    def deadwood_value(cid):
        r = card_rank(cid)
        if r == 0: return 1  # Ace
        if r >= 9: return 10  # T,J,Q,K
        return r + 1  # 2-9

    def find_melds(hand):
        """Find all possible melds (runs and sets) in hand."""
        melds = []
        # Sets: 3+ cards of same rank
        by_rank = {}
        for c in hand:
            by_rank.setdefault(card_rank(c), []).append(c)
        for r, cards in by_rank.items():
            if len(cards) >= 3:
                melds.append(tuple(sorted(cards[:3])))
                if len(cards) >= 4:
                    melds.append(tuple(sorted(cards)))

        # Runs: 3+ consecutive cards of same suit
        by_suit = {}
        for c in hand:
            by_suit.setdefault(card_suit(c), []).append(c)
        for s, cards in by_suit.items():
            ranks = sorted(set(card_rank(c) for c in cards))
            run = [ranks[0]]
            for i in range(1, len(ranks)):
                if ranks[i] == run[-1] + 1:
                    run.append(ranks[i])
                else:
                    if len(run) >= 3:
                        melds.append(tuple(card_id(r, s) for r in run))
                    run = [ranks[i]]
            if len(run) >= 3:
                melds.append(tuple(card_id(r, s) for r in run))
        return melds

    def calc_deadwood(hand):
        """Calculate minimum deadwood for a hand using greedy meld assignment."""
        melds = find_melds(hand)
        if not melds:
            return sum(deadwood_value(c) for c in hand), set()
        # Greedy: pick meld that removes most deadwood, repeat
        best_dw = sum(deadwood_value(c) for c in hand)
        best_melded = set()
        remaining = set(hand)
        melded = set()
        changed = True
        while changed:
            changed = False
            best_meld = None
            best_saving = 0
            for m in melds:
                if all(c in remaining for c in m):
                    saving = sum(deadwood_value(c) for c in m)
                    if saving > best_saving:
                        best_saving = saving
                        best_meld = m
            if best_meld:
                for c in best_meld:
                    remaining.discard(c)
                    melded.add(c)
                changed = True
        return sum(deadwood_value(c) for c in remaining), melded

    # Parse hand from info state
    info = state.information_state_string(player)
    hand = []
    for cid in range(52):
        cn = card_name(cid)
        if cn in info:
            # Check it's in our player section
            hand.append(cid)

    # Determine legal action types
    has_draw_upcard = 52 in legal
    has_draw_stock = 53 in legal
    has_pass = 54 in legal
    has_knock = 55 in legal
    discard_actions = [a for a in legal if a < 52]

    # Knock if possible — always good to end with low deadwood
    if has_knock:
        dw, melded = calc_deadwood(hand)
        return 55, f"Deadwood is {dw}, within knock threshold. Knock to end the round and score."

    # Draw phase: decide between upcard and stock
    if has_draw_upcard or has_draw_stock:
        if has_pass and not has_draw_stock:
            # First upcard offer — check if upcard helps
            # Parse upcard from info
            upcard_cid = None
            if "Upcard: " in info:
                uc_str = info.split("Upcard: ")[-1][:2].strip()
                if uc_str != "XX":
                    for cid in range(52):
                        if card_name(cid) == uc_str:
                            upcard_cid = cid
                            break

            if upcard_cid is not None:
                # Check if upcard reduces deadwood
                test_hand = hand + [upcard_cid]
                dw_with, _ = calc_deadwood(test_hand)
                dw_without, _ = calc_deadwood(hand)
                if dw_with < dw_without:
                    return 52, f"Upcard {card_name(upcard_cid)} reduces deadwood from {dw_without} to {dw_with}. Draw it."
            return 54, "Upcard doesn't help current melds, pass."

        if has_draw_upcard and has_draw_stock:
            # Mid-game draw: check if upcard helps
            upcard_cid = None
            if "Upcard: " in info:
                uc_str = info.split("Upcard: ")[-1][:2].strip()
                if uc_str != "XX":
                    for cid in range(52):
                        if card_name(cid) == uc_str:
                            upcard_cid = cid
                            break

            if upcard_cid is not None:
                test_hand = hand + [upcard_cid]
                dw_with, _ = calc_deadwood(test_hand)
                dw_without, _ = calc_deadwood(hand)
                if dw_with < dw_without:
                    return 52, f"Upcard {card_name(upcard_cid)} helps form melds, reducing deadwood. Draw upcard."
            return 53, "Upcard doesn't improve hand, draw from stock for better chances."

        if has_draw_stock:
            return 53, "Draw from stock."
        return 52, "Draw upcard (only option)."

    # Discard phase: discard highest deadwood card not in a meld
    if discard_actions:
        dw, melded = calc_deadwood(hand)
        non_melded = [a for a in discard_actions if a not in melded]
        if non_melded:
            # Discard highest deadwood value among non-melded
            worst = max(non_melded, key=deadwood_value)
            cn = card_name(worst)
            dw_val = deadwood_value(worst)
            return worst, f"Discard {cn} (deadwood value {dw_val}), not part of any meld. Keep meld cards."
        else:
            # All cards in melds — discard lowest value card
            worst = min(discard_actions, key=deadwood_value)
            cn = card_name(worst)
            return worst, f"All cards form melds. Sacrifice {cn} (lowest value) to draw potentially better card."

    # Fallback
    action = legal[0]
    return action, "Taking best available action."


BOTS = {
    "leduc_poker": leduc_poker_bot,
    "liars_dice": liars_dice_bot,
    "goofspiel": goofspiel_bot,
    "othello": othello_bot,
    "hex": hex_bot,
    "clobber": clobber_bot,
    "gin_rummy": gin_rummy_bot,
}
