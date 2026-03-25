"""Liar's Dice bot v4: MCTS action + call-liar emphasis.

Same MCTS for action selection as liars_dice_bot.py.
Think always explains decision using probability framework.
Key fix: explicitly teaches WHEN and WHY to call liar.

Training data from this bot will have higher call_liar representation
by generating games where the bot is Player 1 (responder) more often.
"""

import random
from mcts_helper import get_mcts_bot, mcts_step_with_stats


def _parse_dice_and_bid(state, player):
    """Parse player's dice and current bid from info state."""
    info = state.information_state_string(player)
    parts = info.split() if info else []

    dice = []
    if parts:
        dice = [int(c) for c in parts[0] if c.isdigit()]

    freq = {}
    for d in dice:
        freq[d] = freq.get(d, 0) + 1
    wild_count = freq.get(6, 0)

    def support(face):
        return freq.get(face, 0) + (wild_count if face != 6 else 0)

    bids = [p for p in parts[1:] if '-' in p] if len(parts) > 1 else []
    last_qty, last_face = 0, 0
    if bids:
        try:
            last_qty = int(bids[-1].split('-')[0])
            last_face = int(bids[-1].split('-')[1])
        except (ValueError, IndexError):
            pass

    num_dice = len(dice) if dice else 5
    opp_dice = num_dice * 2 - num_dice  # total - mine

    return dice, freq, wild_count, support, last_qty, last_face, num_dice, opp_dice


def _prob(needed, opp_n):
    """P(opponent has >= needed matching dice out of opp_n), p=1/3 each."""
    if needed <= 0:
        return 1.0
    if needed > opp_n:
        return 0.0
    from math import comb
    p = 1.0 / 3.0
    total = 0.0
    for k in range(needed, opp_n + 1):
        total += comb(opp_n, k) * (p ** k) * ((1 - p) ** (opp_n - k))
    return total


def _rule_think(action, state, player, legal, dice, freq, wild_count,
                support, last_qty, last_face, num_dice, opp_dice):
    """Always explain using probability framework."""
    liar_action = max(legal)
    is_call = (action == liar_action)
    dice_str = ", ".join(str(d) for d in sorted(dice))

    # Hand summary
    hand_parts = []
    for face in range(1, 7):
        cnt = freq.get(face, 0)
        if cnt > 0:
            if face == 6:
                hand_parts.append(f"{cnt} wild(6)")
            else:
                s = support(face)
                hand_parts.append(f"{cnt}x{face}+{wild_count}w={s}" if wild_count else f"{cnt}x{face}={s}")
    hand = f"My dice [{dice_str}]: {', '.join(hand_parts)}. 6s are wild."

    if is_call and last_qty > 0:
        my_match = support(last_face)
        needed = last_qty - my_match
        prob = _prob(needed, opp_dice)
        pct = int(prob * 100)
        confidence = "very unlikely" if pct < 15 else "unlikely" if pct < 30 else "possible" if pct < 50 else "likely"

        return (f"{hand} "
                f"Opponent bid {last_qty}x face {last_face}. "
                f"I have {my_match} matching ({freq.get(last_face, 0)} actual + {wild_count} wild). "
                f"Opponent needs {needed} of their {opp_dice} dice to match — "
                f"probability {pct}% ({confidence}). "
                f"CALL LIAR — the bid is {'almost certainly' if pct < 15 else 'probably'} false.")

    elif not is_call:
        bid_str = state.action_to_string(player, action)
        try:
            bp = bid_str.split('-')
            bid_qty, bid_face = int(bp[0]), int(bp[1])
        except Exception:
            bid_qty, bid_face = 0, 0

        my_sup = support(bid_face) if bid_face > 0 else 0
        needed_from_opp = max(0, bid_qty - my_sup)
        opp_prob = _prob(needed_from_opp, opp_dice)
        opp_pct = int(opp_prob * 100)

        if last_qty == 0:
            return (f"{hand} "
                    f"Opening bid {bid_qty}x{bid_face}. "
                    f"I have {my_sup} support for face {bid_face}. "
                    f"Need {needed_from_opp} from opponent ({opp_pct}% likely). "
                    f"Strong opening — forces opponent to overbid or call blindly.")
        else:
            call_match = support(last_face)
            call_needed = last_qty - call_match
            call_prob = _prob(call_needed, opp_dice)
            call_pct = int(call_prob * 100)

            return (f"{hand} "
                    f"Opponent bid {last_qty}x{last_face}. "
                    f"If I call: opponent needs {call_needed} matches ({call_pct}% they have it). "
                    f"Instead raising to {bid_qty}x{bid_face}: I have {my_sup} support, "
                    f"need {needed_from_opp} from opponent ({opp_pct}% likely). "
                    f"Raising is better — pressures opponent with a bid I can back up.")

    return f"{hand} Taking best available action."


def liars_dice_call_bot(state, player):
    """MCTS action + rule-based probability think."""
    legal = state.legal_actions(player)
    if len(legal) <= 1:
        return legal[0], "Only one legal action available."

    dice, freq, wild_count, support, last_qty, last_face, num_dice, opp_dice = \
        _parse_dice_and_bid(state, player)

    # Use MCTS for action selection
    game = state.get_game()
    bot = get_mcts_bot(game, "liars_dice")

    action = None
    if bot is not None:
        try:
            action, _, _ = mcts_step_with_stats(bot, state)
            if action not in legal:
                action = None
        except Exception:
            action = None
    if action is None:
        action = legal[0]

    think = _rule_think(action, state, player, legal, dice, freq, wild_count,
                        support, last_qty, last_face, num_dice, opp_dice)
    return action, think
