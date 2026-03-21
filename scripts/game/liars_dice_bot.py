"""Liar's Dice bot: minimal learnable strategy set.

NOT designed to beat MCTS (impossible at 3000sim).
Designed to produce training data that teaches the model
5 high-certainty rules for making correct decisions.

Rules:
1. MUST CALL: opponent bid impossible (need 4+ from 5 dice)
2. MUST BID: strong support (3+ matching including wilds)
3. OPENING: bid at own support level on strongest face
4. ESCALATION: follow opponent's face if we also support it, call if we don't
5. WILDS: count 6s as wilds for any face, never bid on face 6
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

    # Calculate support for each face
    def support(face):
        return freq.get(face, 0) + (wild_count if face != 6 else 0)

    best_face = max(range(1, 6), key=support)  # exclude 6 (Rule 5)
    best_support = support(best_face)

    # ===== RULE 1: MUST CALL — opponent bid is impossible =====
    if last_bid_qty > 0:
        my_matching = support(last_bid_face)
        needed_from_opp = last_bid_qty - my_matching

        if needed_from_opp >= 4:
            # Opponent needs 4+ of their 5 dice to match — virtually impossible
            return liar_action, (
                f"Rule: MUST CALL. My dice [{dice_str}] have {my_matching} matching face {last_bid_face}. "
                f"Opponent's bid of {last_bid_qty}x{last_bid_face} requires them to have {needed_from_opp} "
                f"matching dice out of {opponent_dice} — that's nearly impossible. Calling liar with high confidence.")

        if needed_from_opp >= 3:
            # Opponent needs 3 of 5 — unlikely (~20%)
            return liar_action, (
                f"Rule: LIKELY CALL. My dice [{dice_str}] provide {my_matching} support for face {last_bid_face}. "
                f"Opponent needs {needed_from_opp} of their {opponent_dice} dice to match. "
                f"With each die having roughly 1/3 chance, this is only about 20% likely. Calling liar.")

    # ===== RULE 3: OPENING — bid at own support level =====
    if last_bid_qty == 0 and non_liar:
        # First bid: bid conservatively on strongest face
        target_qty = best_support  # bid exactly what we can prove
        best_bid = None
        for a in non_liar:
            try:
                bid_str = state.action_to_string(player, a)
                if '-' not in bid_str: continue
                bq, bf = int(bid_str.split('-')[0]), int(bid_str.split('-')[1])
                if bf == best_face and bq <= target_qty:
                    best_bid = a
            except:
                pass

        if best_bid is None:
            # Fallback: pick lowest bid on best face
            for a in non_liar:
                try:
                    bid_str = state.action_to_string(player, a)
                    if '-' not in bid_str: continue
                    bq, bf = int(bid_str.split('-')[0]), int(bid_str.split('-')[1])
                    if bf == best_face:
                        best_bid = a
                        break
                except:
                    pass

        if best_bid is None:
            best_bid = non_liar[0]

        bid_str = state.action_to_string(player, best_bid)
        wild_note = f" plus {wild_count} wild 6s" if wild_count > 0 else ""
        return best_bid, (
            f"Rule: OPENING BID. My dice [{dice_str}] — I have {freq.get(best_face, 0)} "
            f"{best_face}s{wild_note}, giving {best_support} effective support. "
            f"Bidding {bid_str} which I can back up with my own dice. "
            f"This is a safe opening that forces opponent to either raise or accept.")

    # ===== RULE 2 & 4: RESPOND to opponent bid =====
    if last_bid_qty > 0 and non_liar:
        my_matching = support(last_bid_face)

        # Rule 4a: If opponent bid on OUR strong face, we can raise
        if last_bid_face == best_face and best_support > last_bid_qty:
            # We can safely raise on this face
            target_qty = min(best_support, last_bid_qty + 1)
            best_bid = None
            for a in non_liar:
                try:
                    bid_str = state.action_to_string(player, a)
                    if '-' not in bid_str: continue
                    bq, bf = int(bid_str.split('-')[0]), int(bid_str.split('-')[1])
                    if bf == best_face and bq <= target_qty + 1:
                        best_bid = a
                        break
                except:
                    pass

            if best_bid:
                bid_str = state.action_to_string(player, best_bid)
                return best_bid, (
                    f"Rule: RAISE ON STRENGTH. My dice [{dice_str}] have {best_support} "
                    f"support for face {best_face} (opponent also bid this face). "
                    f"Raising to {bid_str} is backed by my strong holding. "
                    f"Opponent's bid confirms there are many {best_face}s in play.")

        # Rule 4b: Opponent bid a face we DON'T have — switch to our strong face
        if my_matching <= 1 and best_support >= 2:
            # Switch to our face
            best_bid = None
            for a in non_liar:
                try:
                    bid_str = state.action_to_string(player, a)
                    if '-' not in bid_str: continue
                    bq, bf = int(bid_str.split('-')[0]), int(bid_str.split('-')[1])
                    if bf == best_face and bq <= best_support + 1:
                        best_bid = a
                        break
                except:
                    pass

            if best_bid:
                bid_str = state.action_to_string(player, best_bid)
                return best_bid, (
                    f"Rule: SWITCH FACE. Opponent bid on face {last_bid_face} but I have "
                    f"only {my_matching} matching. Switching to face {best_face} where I "
                    f"have {best_support} support [{dice_str}]. Bidding {bid_str}.")

        # Rule 2: We have strong support, bid it
        if best_support >= 3:
            best_bid = None
            for a in non_liar:
                try:
                    bid_str = state.action_to_string(player, a)
                    if '-' not in bid_str: continue
                    bq, bf = int(bid_str.split('-')[0]), int(bid_str.split('-')[1])
                    if bf == best_face and bq <= best_support:
                        best_bid = a
                except:
                    pass

            if best_bid:
                bid_str = state.action_to_string(player, best_bid)
                wild_note = f" (including {wild_count} wilds)" if wild_count > 0 else ""
                return best_bid, (
                    f"Rule: BID ON STRENGTH. My dice [{dice_str}] give me {best_support} "
                    f"effective {best_face}s{wild_note}. Bidding {bid_str} is well-supported "
                    f"and puts pressure on opponent to either match or call.")

    # ===== FALLBACK: Call or minimal bid =====
    if last_bid_qty > 0:
        my_matching = support(last_bid_face)
        needed = last_bid_qty - my_matching
        if needed >= 2:
            return liar_action, (
                f"Rule: DEFAULT CALL. My dice [{dice_str}] have only {my_matching} support "
                f"for opponent's bid of {last_bid_qty}x{last_bid_face}. Opponent needs "
                f"{needed} more matching dice — risky for them. Calling liar.")

    # Last resort: pick lowest available bid
    if non_liar:
        action = non_liar[0]
        bid_str = state.action_to_string(player, action)
        return action, (
            f"No strong option available with dice [{dice_str}]. Making minimum bid "
            f"{bid_str} to stay in the game and gather more information about opponent's hand.")

    return liar_action, f"Forced to call liar with dice [{dice_str}]. No viable bids remain."
