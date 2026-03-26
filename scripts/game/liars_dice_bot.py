"""Liar's Dice bot v4: MCTS action selection + hand-aware think chains.

v3→v4 changes:
- ALWAYS use hand-aware Step 1/2/3 think chains (never MCTS stats think)
- Opening bids: clamp to reasonable range (qty ≤ support + 2)
- Opening bid face: prefer strongest face in hand
- More borderline call_liar situations in data

Every turn follows the SAME decision framework (learnable by SFT):
Step 1: Count my support for the current bid face (actual + wild 6s)
Step 2: Calculate how many opponent needs (bid_qty - my_support)
Step 3: Estimate probability (each die ~33% chance of matching)
Step 4: Decision rule:
  - If P(opponent has enough) < 25%: CALL LIAR
  - If I have strong support (3+): RAISE on my strongest face
  - Otherwise: raise minimally or call based on risk

Key: 6s are WILD (count as any face). Never bid face 6 directly.
"""

import random
from mcts_helper import get_mcts_bot, mcts_step_with_stats, format_mcts_think


def _get_game_context(action, state, player, legal, liar_action,
                      last_bid_qty, last_bid_face, dice, freq, wild_count, support):
    """Get short game-specific context for the chosen action."""
    is_call = (action == liar_action)

    if is_call:
        if last_bid_qty > 0:
            my_matching = support(last_bid_face)
            needed = last_bid_qty - my_matching
            if needed >= 3:
                return "Opponent's bid is improbable."
            else:
                return "Opponent's bid is borderline — calling to test it."
        return ""

    # It's a bid
    try:
        bid_str = state.action_to_string(player, action)
        bid_parts = bid_str.split('-')
        bid_face = int(bid_parts[1])
        my_support = support(bid_face)
    except Exception:
        my_support = 0

    if last_bid_qty == 0:
        return "Strong opening position."
    if my_support >= 3:
        return "My dice support this bid."
    return ""


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

    # Use MCTS for action selection only (think chains are ALWAYS hand-aware)
    game = state.get_game()
    bot = get_mcts_bot(game, "liars_dice")
    action = None

    if bot is not None:
        try:
            action, mcts_stats, root = mcts_step_with_stats(bot, state)
            if action not in legal:
                action = None
        except Exception:
            action = None

    if action is None:
        action = legal[0]

    # === OPENING BID OVERRIDE ===
    # Clamp unreasonable opening bids to hand-aware range
    if last_bid_qty == 0 and action != liar_action:
        best_face = max(range(1, 6), key=support)
        best_support = support(best_face)
        max_reasonable_qty = min(best_support + 2, total_dice)

        try:
            bid_str = state.action_to_string(player, action)
            bid_parts = bid_str.split('-')
            mcts_qty = int(bid_parts[0])
            # If MCTS selected an unreasonable bluff, override
            if mcts_qty > max_reasonable_qty:
                # Find best legal action: bid best_support x best_face
                target_qty = max(1, best_support)
                for a in legal:
                    if a == liar_action:
                        continue
                    try:
                        a_str = state.action_to_string(player, a)
                        a_parts = a_str.split('-')
                        a_qty, a_face = int(a_parts[0]), int(a_parts[1])
                        if a_face == best_face and a_qty == target_qty:
                            action = a
                            break
                    except Exception:
                        continue
                else:
                    # Fallback: find any bid with qty ≤ max_reasonable_qty on best_face
                    for a in legal:
                        if a == liar_action:
                            continue
                        try:
                            a_str = state.action_to_string(player, a)
                            a_parts = a_str.split('-')
                            a_qty, a_face = int(a_parts[0]), int(a_parts[1])
                            if a_qty <= max_reasonable_qty and a_face == best_face:
                                action = a
                                break
                        except Exception:
                            continue
        except Exception:
            pass

    # === CALL LIAR OVERRIDE ===
    # If opponent's bid is very improbable, override MCTS to call liar
    opp_dice = total_dice - num_dice
    if last_bid_qty > 0 and action != liar_action:
        my_matching = support(last_bid_face)
        needed = last_bid_qty - my_matching
        if needed > opp_dice:
            # Impossible — always call
            action = liar_action
        elif needed >= 3:
            # Very improbable — call liar
            from math import comb
            p = 1.0 / 3.0
            prob = sum(comb(opp_dice, k) * (p**k) * ((1-p)**(opp_dice-k))
                      for k in range(needed, opp_dice+1))
            if prob < 0.15:
                action = liar_action

    # === ALWAYS use hand-aware think chains (NEVER MCTS stats think) ===

    # Rule-based probability explanation
    is_call = (action == liar_action)

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

    # === FIXED DECISION FRAMEWORK (same structure every turn) ===
    # Step 1: Hand analysis
    hand_parts = []
    for face in range(1, 7):
        cnt = freq.get(face, 0)
        if cnt > 0:
            if face == 6:
                hand_parts.append(f"{cnt} wild(6)")
            else:
                s = support(face)
                hand_parts.append(f"{cnt}x{face}" + (f"+{wild_count}w={s}" if wild_count > 0 else f"={s}"))

    hand_info = f"My dice [{dice_str}]: {', '.join(hand_parts)}. Wild 6s count as any face."

    if is_call and last_bid_qty > 0:
        my_matching = support(last_bid_face)
        needed = last_bid_qty - my_matching
        prob = _approx_prob(needed, opp_dice)
        prob_pct = int(prob * 100)

        # Fixed framework: Step 1 → Step 2 → Step 3 → Decision
        think = (f"Step 1: {hand_info} "
                f"Step 2: Opponent bid {last_bid_qty}x face {last_bid_face}. "
                f"I have {my_matching} support ({freq.get(last_bid_face, 0)} actual + {wild_count} wilds). "
                f"Opponent needs {needed} of their {opp_dice} dice to match. "
                f"Step 3: Each die has ~33% chance (face {last_bid_face} or wild 6). "
                f"P(opponent has {needed}+) = {prob_pct}%. "
                f"Decision: {prob_pct}% is {'very low' if prob_pct < 20 else 'low' if prob_pct < 35 else 'borderline'} "
                f"→ CALL LIAR. The bid is likely false.")

    elif not is_call:
        bid_str = state.action_to_string(player, action)
        try:
            bid_parts = bid_str.split('-')
            bid_qty, bid_face = int(bid_parts[0]), int(bid_parts[1])
        except Exception:
            bid_qty, bid_face = 0, 0

        my_support_bid = support(bid_face) if bid_face > 0 else 0
        needed_from_opp = max(0, bid_qty - my_support_bid)
        opp_prob = _approx_prob(needed_from_opp, opp_dice)
        opp_pct = int(opp_prob * 100)

        best_face = max(range(1, 6), key=support)
        best_support = support(best_face)

        if last_bid_qty == 0:
            # Opening
            think = (f"Step 1: {hand_info} "
                    f"Step 2: Opening bid. Strongest face: {best_face} with {best_support} support. "
                    f"Step 3: Bidding {bid_qty}x{bid_face}. I back {my_support_bid} myself, "
                    f"need {needed_from_opp} from opponent ({opp_pct}% likely). "
                    f"Decision: BID {bid_qty}x{bid_face}. This is credible (backed by my dice) "
                    f"and forces opponent to either overbid or challenge blindly.")
        else:
            # Responding — explain why raise instead of call
            call_my = support(last_bid_face)
            call_needed = last_bid_qty - call_my
            call_prob = _approx_prob(call_needed, opp_dice)
            call_pct = int(call_prob * 100)

            think = (f"Step 1: {hand_info} "
                    f"Step 2: Opponent bid {last_bid_qty}x{last_bid_face}. "
                    f"Option A (call): opponent needs {call_needed} matches ({call_pct}% they have it). "
                    f"Option B (raise to {bid_qty}x{bid_face}): I have {my_support_bid} support, "
                    f"need {needed_from_opp} from opponent ({opp_pct}% likely). "
                    f"Step 3: {'Calling is risky (' + str(call_pct) + '% opponent succeeds)' if call_pct > 40 else 'Could call, but'} "
                    f"raising to {bid_qty}x{bid_face} is better — "
                    f"{'I have {0} support backing this bid'.format(my_support_bid) if my_support_bid >= 2 else 'this pressures opponent into a harder decision'}. "
                    f"Decision: RAISE to {bid_qty}x{bid_face}.")
    else:
        think = f"Step 1: {hand_info} Decision: taking available action."

    return action, think
