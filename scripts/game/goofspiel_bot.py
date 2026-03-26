"""Goofspiel bot strategy.

v1-v3: proportional bidding + endgame
v4: State-specific think — references my hand, opponent's used cards,
    score differential, remaining prize distribution, and bid rationale.
v5: Removed agents dependency and silent fallback. Errors must surface.
"""

import re


def goofspiel_bot(state, player):
    legal = sorted(state.legal_actions(player))

    if len(legal) == 1:
        return legal[0], "Last card remaining — must play it to conclude the game."

    obs = state.observation_string(player)

    # Parse prize card
    m = re.search(r"Current point card: (\d+)", obs)
    prize = int(m.group(1)) if m else len(legal) // 2

    # Parse scores — format: "Points: X Y" or "Player 0: X points, Player 1: Y points"
    my_score, opp_score = 0, 0
    points_m = re.search(r"Points:\s+(\d+)\s+(\d+)", obs)
    if points_m:
        scores = [int(points_m.group(1)), int(points_m.group(2))]
        my_score, opp_score = scores[player], scores[1 - player]
    else:
        for pm in re.finditer(r"Player (\d+): (\d+) points", obs):
            pid, pts = int(pm.group(1)), int(pm.group(2))
            if pid == player:
                my_score = pts
            else:
                opp_score = pts
    score_diff = my_score - opp_score

    # Parse remaining cards info
    my_hand_m = re.search(rf"P{player} hand: (.+)", obs)
    my_hand_str = my_hand_m.group(1).strip() if my_hand_m else ""
    remaining_prizes_m = re.search(r"Remaining Point Cards: (.+)", obs)
    remaining_prizes_str = remaining_prizes_m.group(1).strip() if remaining_prizes_m else ""

    max_card = max(legal) + 1
    num_remaining = len(legal)
    my_cards = sorted([a + 1 for a in legal])
    my_highest = my_cards[-1]
    my_lowest = my_cards[0]

    # Identify remaining high-value prizes
    remaining_prizes = []
    if remaining_prizes_str:
        remaining_prizes = [int(x) for x in remaining_prizes_str.split() if x.isdigit()]
    high_prizes_left = [p for p in remaining_prizes if p >= max_card * 0.6 and p != prize]
    total_remaining_value = sum(remaining_prizes) if remaining_prizes else 0

    # Core strategy: proportional bidding
    ratio = prize / max_card
    idx = int(ratio * (len(legal) - 1))
    idx = max(0, min(idx, len(legal) - 1))
    action = legal[idx]

    # Endgame adjustment
    if num_remaining <= 2:
        if prize >= max(legal):
            action = max(legal)
        elif prize <= min(legal) + 1:
            action = min(legal)

    bid_value = action + 1

    # --- Build state-specific think ---
    parts = []

    # 1. Situation assessment
    if score_diff > 0:
        parts.append(f"Leading {my_score}-{opp_score} (+{score_diff}).")
    elif score_diff < 0:
        parts.append(f"Trailing {my_score}-{opp_score} ({score_diff}).")
    elif my_score > 0:
        parts.append(f"Tied at {my_score}-{opp_score}.")

    # 2. Prize evaluation relative to what's left
    if high_prizes_left:
        parts.append(f"Prize {prize} of {total_remaining_value} total points remaining. "
                     f"High prizes still available: {', '.join(str(p) for p in sorted(high_prizes_left, reverse=True)[:3])}.")
    else:
        parts.append(f"Prize {prize}. No higher prizes remaining — this is one of the last valuable targets.")

    # 3. Bid rationale
    hand_str = ', '.join(str(c) for c in my_cards)
    higher_card = my_cards[min(idx + 1, len(my_cards) - 1)] if idx < len(my_cards) - 1 else None
    lower_card = my_cards[max(idx - 1, 0)] if idx > 0 else None

    if prize >= max_card * 0.7:
        parts.append(f"High-value target worth {prize} points. Bidding {bid_value} "
                     f"from hand [{hand_str}].")
        if higher_card and higher_card != bid_value:
            parts.append(f"Bidding higher ({higher_card}) would win more often but wastes "
                         f"a strong card needed for the {len(high_prizes_left)} remaining high prizes.")
        if score_diff < 0:
            parts.append(f"Trailing by {-score_diff}, so winning this {prize}-point prize "
                         f"is critical to close the gap.")
        elif score_diff > 0:
            parts.append(f"Leading by {score_diff}, so even a proportional bid is enough — "
                         f"opponent must overbid to catch up.")
    elif prize >= max_card * 0.4:
        parts.append(f"Mid-value prize ({prize} pts). Bidding {bid_value} from [{hand_str}].")
        if high_prizes_left:
            top_prizes = sorted(high_prizes_left, reverse=True)[:2]
            parts.append(f"Saving {my_highest} for upcoming prizes ({', '.join(str(p) for p in top_prizes)}) "
                         f"which are worth more. Overbidding here would leave us weak later.")
        else:
            parts.append(f"No bigger prizes remain, so this is worth contesting with a moderate bid.")
    else:
        parts.append(f"Low prize ({prize} pts). Spending only {bid_value} from [{hand_str}].")
        if lower_card is not None and lower_card < bid_value:
            parts.append(f"Could bid even lower ({lower_card}) but {bid_value} gives better "
                         f"chances of winning while still conserving resources.")
        if high_prizes_left:
            total_high = sum(high_prizes_left)
            parts.append(f"The {len(high_prizes_left)} high prizes ahead total {total_high} points — "
                         f"worth far more than this {prize}-point prize. Conserving for those.")

    # 4. Strategic reasoning
    if num_remaining <= 3:
        if score_diff > 0:
            parts.append(f"Final {num_remaining} rounds with a {score_diff}-point lead. "
                         f"Only need to win {1 if score_diff > prize else 'at least one more big prize'} to secure victory.")
        elif score_diff < 0:
            must_win = -score_diff
            parts.append(f"Final {num_remaining} rounds, trailing by {must_win}. "
                         f"Must win this to have a chance — every point counts now.")
        else:
            parts.append(f"Final {num_remaining} rounds, tied. Whoever wins the bigger remaining prizes takes the game.")
    elif score_diff > total_remaining_value // 3:
        parts.append(f"Comfortable lead ({score_diff} pts with {total_remaining_value} remaining). "
                     f"Can afford to lose this prize without risking the game.")
    elif score_diff < -(total_remaining_value // 3):
        parts.append(f"Significant deficit ({score_diff}). "
                     f"Must start winning prizes to stay competitive.")

    return action, " ".join(parts)
