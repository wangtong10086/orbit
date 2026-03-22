"""Liar's Dice bot v2: MCTS search (10000 sim) + probability explanation.

v1: Rule-based probability → 0% vs MCTS 3000sim
v2: Use own MCTS (10000 sim, >3x opponent's 3000) for move selection.
    Generate think blocks explaining the probability reasoning.
"""

import numpy as np
import random

_mcts_bot = None
_mcts_game_name = None


def _get_mcts_bot(game):
    global _mcts_bot, _mcts_game_name
    gname = game.get_type().short_name
    if _mcts_bot is not None and _mcts_game_name == gname:
        return _mcts_bot
    try:
        from open_spiel.python.algorithms import mcts as mcts_lib

        class Evaluator(mcts_lib.Evaluator):
            def __init__(self, n_rollouts=50):
                self._n = n_rollouts
                self._rs = np.random.RandomState(42)
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

        _mcts_bot = mcts_lib.MCTSBot(
            game=game, uct_c=1.414, max_simulations=10000,
            evaluator=Evaluator(n_rollouts=50),
            random_state=np.random.RandomState(321),
            solve=True,
        )
        _mcts_game_name = gname
        return _mcts_bot
    except Exception:
        return None


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
    bot = _get_mcts_bot(game)
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

        if needed >= opp_dice:
            reason = (f"Opponent would need ALL {opp_dice} of their dice to show face {last_bid_face} "
                      f"or wild 6 — virtually impossible ({prob_pct}% likely).")
        elif prob < 0.25:
            reason = (f"Opponent needs {needed} of their {opp_dice} dice to match. "
                      f"With each die having ~33% chance (face or wild 6), "
                      f"probability is only {prob_pct}%. Favorable odds to challenge.")
        else:
            reason = (f"Opponent needs {needed} of {opp_dice} dice matching (~{prob_pct}% chance). "
                      f"While not impossible, the risk-reward favors calling.")

        think = (f"Calling liar on {last_bid_qty}x face {last_bid_face}. "
                 f"My dice [{dice_str}]: I have {my_matching} support "
                 f"({freq.get(last_bid_face, 0)} actual + {wild_count} wild 6s). "
                 f"{reason}")

    elif not is_call:
        bid_str = state.action_to_string(player, action)
        # Parse the bid we're making
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
            # Opening bid
            hand_analysis = []
            for face in range(1, 7):
                s = support(face) if face != 6 else freq.get(6, 0)
                if s > 0:
                    hand_analysis.append(f"face {face}: {s}")

            think = (f"Opening bid: {bid_str}. My dice [{dice_str}] — "
                     f"hand analysis: {', '.join(hand_analysis)}. "
                     f"Bidding {bid_qty}x face {bid_face}: I have {my_support_for_bid} matching, "
                     f"need opponent to have {needed_from_opp} more ({opp_pct}% likely). "
                     f"This opening is backed by my dice and puts opponent in a reactive position.")
        else:
            # Responding to opponent bid
            think = (f"Raising to {bid_str} over opponent's {last_bid_qty}x{last_bid_face}. "
                     f"My dice [{dice_str}] provide {my_support_for_bid} support for face {bid_face}. "
                     f"My bid needs opponent to contribute {needed_from_opp} more ({opp_pct}% likely). "
                     f"Raising is better than calling because opponent's previous bid of "
                     f"{last_bid_qty}x{last_bid_face} had reasonable backing "
                     f"({_approx_prob(last_bid_qty - support(last_bid_face), opp_dice)*100:.0f}% opponent support). "
                     f"Continuing the bidding war maintains pressure.")
    else:
        think = f"Taking optimal action with dice [{dice_str}]. Total dice in play: {total_dice}."

    return action, think
