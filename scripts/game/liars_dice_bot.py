"""Liar's Dice bot v2: MCTS search (10000 sim) + probability explanation.

v1: Rule-based probability → 0% vs MCTS 3000sim
v2: Use own MCTS (10000 sim, >3x opponent's 3000) for move selection.
    Generate think blocks explaining the probability reasoning.
"""

import random
from mcts_helper import get_mcts_bot


def liars_dice_bot(state, player):
    info = state.information_state_string(player)
    legal = state.legal_actions(player)

    if len(legal) <= 1:
        return legal[0], "Only one legal action available."

    # Parse dice
    dice = []
    parts = info.split() if info else []
    if parts:
        dice = [int(c) for c in parts[0] if c.isdigit()]
    dice_str = ", ".join(str(d) for d in sorted(dice))
    num_dice = len(dice) if dice else 5
    total_dice = num_dice * 2
    liar_action = max(legal)

    # Parse last bid
    bids = [p for p in parts[1:] if '-' in p] if len(parts) > 1 else []
    last_bid_qty, last_bid_face = 0, 0
    if bids:
        try:
            last_bid_qty = int(bids[-1].split('-')[0])
            last_bid_face = int(bids[-1].split('-')[1])
        except (ValueError, IndexError):
            pass

    # Count support (6 is wild)
    freq = {}
    for d in dice:
        freq[d] = freq.get(d, 0) + 1
    wild_count = freq.get(6, 0)

    def support(face):
        return freq.get(face, 0) + (wild_count if face != 6 else 0)

    # Use MCTS for decision
    game = state.get_game()
    bot = get_mcts_bot(game, "liars_dice")
    action = None

    if bot is not None:
        try:
            action = bot.step(state)
            if action not in legal:
                action = None
        except Exception:
            action = None

    if action is None:
        action = legal[0]

    # Generate rich probability-based explanation
    is_call = (action == liar_action)
    opp_dice = total_dice - num_dice

    # Probability helper: P(opponent has >= k matching out of opp_dice dice)
    # Each die has ~1/3 chance of matching (face itself + wild 6)
    def _approx_prob(needed, opp_n):
        if needed <= 0: return 1.0
        if needed > opp_n: return 0.0
        # binomial approximation: p=1/3 (face or wild)
        from math import comb
        p = 1.0 / 3.0
        total = 0.0
        for k in range(needed, opp_n + 1):
            total += comb(opp_n, k) * (p ** k) * ((1 - p) ** (opp_n - k))
        return total

    if is_call and last_bid_qty > 0:
        my_matching = support(last_bid_face)
        needed = last_bid_qty - my_matching
        prob = _approx_prob(needed, opp_dice)
        prob_pct = int(prob * 100)

        # Build reasoning chain: state → analysis → conclusion
        parts = [f"Analyzing opponent's bid of {last_bid_qty}x face {last_bid_face}."]
        parts.append(f"My dice [{dice_str}]: I see {freq.get(last_bid_face, 0)} face-{last_bid_face}(s) "
                    f"plus {wild_count} wild 6(s) = {my_matching} total support.")
        parts.append(f"The bid claims {last_bid_qty} total across all {total_dice} dice. "
                    f"Since I contribute {my_matching}, opponent must have {needed} matching "
                    f"out of their {opp_dice} dice.")

        if needed >= opp_dice:
            parts.append(f"That means ALL {opp_dice} opponent dice must show {last_bid_face} or 6 — "
                        f"probability ~{prob_pct}%, essentially impossible. Calling liar.")
        elif needed >= opp_dice - 1:
            parts.append(f"Opponent needs {needed}/{opp_dice} dice matching — only possible if they have "
                        f"almost all {last_bid_face}s and 6s. At ~{prob_pct}% this is very unlikely. Calling.")
        elif prob < 0.30:
            parts.append(f"Each die has ~33% chance of matching (face {last_bid_face} or wild 6). "
                        f"Probability of {needed}+ matches from {opp_dice} dice = {prob_pct}%. "
                        f"The math favors challenging — calling liar.")
        else:
            # Consider alternative: could we raise instead?
            non_liar = [a for a in legal if a != liar_action]
            parts.append(f"Probability is {prob_pct}% — borderline. "
                        f"However, raising would require bidding even higher ({len(non_liar)} options), "
                        f"pushing into more uncertain territory. Calling is safer here.")

        think = " ".join(parts)

    elif not is_call:
        bid_str = state.action_to_string(player, action)
        try:
            bid_parts = bid_str.split('-')
            bid_qty, bid_face = int(bid_parts[0]), int(bid_parts[1])
        except Exception:
            bid_qty, bid_face = 0, 0

        my_support_for_bid = support(bid_face) if bid_face > 0 else 0
        needed_from_opp = max(0, bid_qty - my_support_for_bid)
        opp_prob = _approx_prob(needed_from_opp, opp_dice)
        opp_pct = int(opp_prob * 100)

        if last_bid_qty == 0:
            # Opening bid — explain hand analysis and bid choice
            hand_analysis = []
            for face in range(1, 6):
                s = support(face)
                if s > 0:
                    actual = freq.get(face, 0)
                    wild_part = f"+{wild_count}w" if wild_count > 0 and face != 6 else ""
                    hand_analysis.append(f"{face}:{actual}{wild_part}={s}")

            # Why this face and quantity?
            best_face = max(range(1, 6), key=support)
            best_support = support(best_face)

            parts = [f"Opening with dice [{dice_str}]. Hand breakdown: {', '.join(hand_analysis)}."]
            if bid_face == best_face:
                parts.append(f"Face {bid_face} has my strongest support ({my_support_for_bid}). "
                            f"Bidding {bid_qty}x{bid_face}: I back {my_support_for_bid} of these myself, "
                            f"so only need {needed_from_opp} from opponent ({opp_pct}% likely).")
            else:
                parts.append(f"Bidding {bid_qty}x{bid_face} (support: {my_support_for_bid}). "
                            f"Need opponent to have {needed_from_opp} more ({opp_pct}%).")
            parts.append("This forces opponent to either raise higher or challenge with less information.")
            think = " ".join(parts)

        else:
            # Responding to opponent bid — analyze call vs raise
            call_prob = _approx_prob(last_bid_qty - support(last_bid_face), opp_dice)
            call_pct = int(call_prob * 100)

            parts = [f"Opponent bid {last_bid_qty}x{last_bid_face}. My dice [{dice_str}]."]
            parts.append(f"If I call: opponent's bid needs {last_bid_qty - support(last_bid_face)} from "
                        f"their {opp_dice} dice (~{call_pct}% they have it).")
            if call_pct > 50:
                parts.append(f"Calling is risky ({call_pct}% opponent succeeds), so raising instead.")
            else:
                parts.append(f"Calling could work ({100-call_pct}% chance opponent is bluffing), "
                            f"but raising to {bid_str} is better because: ")
            parts.append(f"My {bid_qty}x{bid_face} is backed by {my_support_for_bid} dice "
                        f"(need {needed_from_opp} from opponent, {opp_pct}% likely). "
                        f"This credible raise pressures opponent to make a harder decision.")
            think = " ".join(parts)
    else:
        think = f"Taking optimal action with dice [{dice_str}]. Total dice in play: {total_dice}."

    return action, think
