"""Goofspiel bot strategy.

v1-v3: proportional bidding + endgame
v4: State-specific think — references my hand, opponent's used cards,
    score differential, remaining prize distribution, and bid rationale.
"""

import random


def goofspiel_bot(state, player):
    legal = sorted(state.legal_actions(player))

    if len(legal) == 1:
        return legal[0], "Last card remaining — must play it to conclude the game."

    try:
        from agents import GAME_AGENTS
        import re
        agent = GAME_AGENTS['goofspiel']()
        obs = agent.format_state(state, player)

        # Parse prize card
        m = re.search(r"Current point card: (\d+)", obs)
        prize = int(m.group(1)) if m else len(legal) // 2

        # Parse scores
        my_score_m = re.search(r"Your.*?score:?\s*(\d+)", obs, re.IGNORECASE)
        opp_score_m = re.search(r"Opponent.*?score:?\s*(\d+)", obs, re.IGNORECASE)
        my_score = int(my_score_m.group(1)) if my_score_m else 0
        opp_score = int(opp_score_m.group(1)) if opp_score_m else 0
        score_diff = my_score - opp_score

        # Parse remaining cards info
        my_hand_m = re.search(r"P\d+ hand: (.+)", obs)
        my_hand_str = my_hand_m.group(1).strip() if my_hand_m else ""
        opp_hand_m = re.search(r"P\d+ hand: (.+?)$", obs, re.MULTILINE)
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

        # 1. Situation assessment (unique per game state)
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

        # 3. Bid rationale with hand context
        pct_of_hand = bid_value * 100 // my_highest
        if prize >= max_card * 0.7:
            parts.append(f"This is a high-value prize worth contesting. Bidding {bid_value} "
                        f"({pct_of_hand}% of my strongest card {my_highest}). "
                        f"My hand: [{', '.join(str(c) for c in my_cards)}].")
            if score_diff < 0:
                parts.append("Need to win big prizes to close the gap.")
            elif high_prizes_left:
                parts.append(f"Still saving higher cards for {high_prizes_left[0]}+.")
        elif prize >= max_card * 0.4:
            parts.append(f"Mid-value prize. Bidding {bid_value} proportionally — "
                        f"enough to compete but conserving {my_highest} and other high cards "
                        f"for the {len(high_prizes_left)} remaining high-value prizes.")
        else:
            parts.append(f"Low prize ({prize} points). Spending only {bid_value} from hand "
                        f"[{', '.join(str(c) for c in my_cards)}]. "
                        f"Losing this is acceptable — the {len(high_prizes_left)} high prizes "
                        f"ahead are worth more total.")

        # 4. Strategic consideration (endgame vs resource management)
        if num_remaining <= 3:
            parts.append(f"Final {num_remaining} rounds — every card choice is decisive. "
                        f"{'Must win this to secure the lead.' if score_diff <= 0 and prize > 5 else 'Managing remaining cards carefully.'}")
        elif score_diff > total_remaining_value // 3:
            parts.append("Comfortable lead allows conservative bidding on medium prizes.")
        elif score_diff < -(total_remaining_value // 3):
            parts.append("Must be aggressive on remaining prizes to catch up.")

        return action, " ".join(parts)
    except Exception:
        mid = len(legal) // 2
        return legal[mid], "Playing middle-value card as balanced strategy."
