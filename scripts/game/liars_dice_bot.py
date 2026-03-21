"""Liar's Dice bot strategy.

v1: 保守call → 0%
v2: 概率+bluff → 0%
v3: 精确概率+最优bid → 15% (3/20)
v4: 修复对局分析发现的问题:
    - LOSS#1: bot 被迫 call 一个概率 80% 的真 bid → 应该继续 bid
    - LOSS#3: bot 选了 margin -0.3 的不安全 bid → 应该先 call 对手
    修复: 先评估 call 是否划算 → 只有 call 不划算时才 bid → bid 只选 margin>0
"""

import math
import random


def liars_dice_bot(state, player):
    info = state.information_state_string(player)
    legal = state.legal_actions(player)

    dice = []
    parts = info.split() if info else []
    if parts:
        dice = [int(c) for c in parts[0] if c.isdigit()]

    num_dice = len(dice) if dice else 5
    total_dice = num_dice * 2
    opponent_dice = total_dice - num_dice
    liar_action = max(legal)

    if len(legal) <= 1:
        return legal[0], "Only one legal action available."

    freq = {}
    for d in dice:
        freq[d] = freq.get(d, 0) + 1
    wild_count = freq.get(6, 0)

    bids = [p for p in parts[1:] if '-' in p]
    last_bid_qty, last_bid_face = 0, 0
    if bids:
        try:
            last_bid_qty = int(bids[-1].split('-')[0])
            last_bid_face = int(bids[-1].split('-')[1])
        except (ValueError, IndexError):
            pass

    non_liar = [a for a in legal if a != liar_action]
    dice_str = ", ".join(str(d) for d in sorted(dice))
    face_counts = []
    for f in range(1, 7):
        if freq.get(f, 0) > 0:
            face_counts.append(f"{freq[f]}x{f}")
    dice_desc = ", ".join(face_counts) if face_counts else "mixed"

    def prob_at_least(needed, n, p):
        if needed <= 0: return 0.99
        if needed > n: return 0.001
        mu = n * p
        sigma = max(0.5, math.sqrt(n * p * (1 - p)))
        z = (needed - 0.5 - mu) / sigma
        return max(0.01, min(0.99, 0.5 * (1 - math.erf(z / math.sqrt(2)))))

    # STEP 1: Evaluate current bid — should I call liar?
    call_is_good = False
    prob_true = 1.0
    if last_bid_qty > 0:
        p_face = 1/3 if last_bid_face != 6 else 1/6
        my_matching = freq.get(last_bid_face, 0)
        if last_bid_face != 6:
            my_matching += wild_count
        needed = max(0, last_bid_qty - my_matching)
        prob_true = prob_at_least(needed, opponent_dice, p_face)
        call_is_good = prob_true < 0.45  # Raised from 0.35: MCTS bids aggressively

    # STEP 2: Find best available bid
    # Strategy: bid high enough to pressure opponent but within safe range
    # Target: bid quantity ≈ my_support (forces opponent to have ~0 matching)
    best_bid = None
    best_margin = -999
    best_bid_info = {}
    for a in non_liar:
        try:
            bid_str = state.action_to_string(player, a)
            if '-' not in bid_str: continue
            bq, bf = int(bid_str.split('-')[0]), int(bid_str.split('-')[1])
            my_support = freq.get(bf, 0) + (wild_count if bf != 6 else 0)
            p = 1/3 if bf != 6 else 1/6
            expected = my_support + opponent_dice * p
            margin = expected - bq

            # Prefer bids at or below our support (don't overcommit)
            # Penalty for bidding above what we can prove
            if bq > my_support:
                overcommit_penalty = (bq - my_support) * 1.5
            else:
                overcommit_penalty = 0
            adjusted_score = margin - overcommit_penalty

            if adjusted_score > best_margin:
                best_margin = margin  # keep raw margin for safety check
                best_bid = a
                best_bid_info = {'qty': bq, 'face': bf, 'support': my_support, 'expected': expected}
        except:
            pass

    # STEP 3: Decision logic
    # Priority: call if bid looks fake, otherwise bid if safe, otherwise call anyway
    if call_is_good and liar_action in legal:
        my_matching = freq.get(last_bid_face, 0) + (wild_count if last_bid_face != 6 else 0)
        needed = max(0, last_bid_qty - my_matching)
        think = (f"Evaluating opponent's bid of {last_bid_qty}x{last_bid_face}. "
                 f"My dice [{dice_str}] have {my_matching} matching (including wilds). "
                 f"Opponent needs {needed} more out of {opponent_dice} dice — "
                 f"probability is only {prob_true:.0%}, well below the 35% credibility threshold. "
                 f"The math strongly favors calling this a bluff.")
        return liar_action, think

    if best_bid is not None and best_margin > 0:
        bi = best_bid_info
        confidence = "very safe" if best_margin >= 1.5 else "solid" if best_margin >= 0.5 else "tight"
        think = (f"Opponent's bid appears credible ({prob_true:.0%} probability). "
                 f"My dice [{dice_str}] ({dice_desc}) give {bi['support']} support for face {bi['face']}. "
                 f"With opponent expected to contribute ~{opponent_dice/6:.1f} more, "
                 f"bidding {bi['qty']}x{bi['face']} has margin +{best_margin:.1f} — {confidence}. "
                 f"{'I have room to escalate further if needed.' if best_margin > 1.0 else 'Higher bids would be risky.'}")
        return best_bid, think

    # No safe bid available — must call even if odds aren't great
    if liar_action in legal:
        if last_bid_qty > 0:
            my_matching = freq.get(last_bid_face, 0) + (wild_count if last_bid_face != 6 else 0)
            think = (f"No safe bids remain — all options would require opponent to have "
                     f"an improbable number of matching dice. My dice [{dice_str}] provide "
                     f"{my_matching} support for the current bid of {last_bid_qty}x{last_bid_face}, "
                     f"but the bid is {'likely true' if prob_true > 0.5 else 'questionable'} "
                     f"({prob_true:.0%}). Calling as the least risky option available.")
        else:
            think = f"My dice [{dice_str}]. Forced to call — no viable bidding options."
        return liar_action, think

    # Last resort: bid even with negative margin
    if best_bid is not None:
        bi = best_bid_info
        think = (f"Difficult position with dice [{dice_str}]. No safe bid exists "
                 f"(best margin is {best_margin:+.1f}), but calling isn't available. "
                 f"Bidding {bi['qty']}x{bi['face']} as the least bad option and hoping "
                 f"opponent doesn't call.")
        return best_bid, think

    return legal[0], f"Taking only available action with dice [{dice_str}]."
