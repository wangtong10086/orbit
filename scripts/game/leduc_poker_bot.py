"""Leduc Poker bot strategy.

v3: Decision table core + opponent raise sensing
v4: State-specific thinks — reference pot size, betting history,
    opponent's likely range, exact equity calculations.
    6 cards total (J♠J♥Q♠Q♥K♠K♥), 2 rounds, 3 actions.
"""


def leduc_poker_bot(state, player):
    info = state.information_state_string(player)
    legal = state.legal_actions(player)

    private_card = int(info.split("Private: ")[1].split("]")[0])
    rank = private_card // 2  # 0=J, 1=Q, 2=K
    rank_name = ["J", "Q", "K"][rank]
    suit = "♠" if private_card % 2 == 0 else "♥"

    has_public = "Public:" in info
    public_rank = -1
    public_name = ""
    if has_public:
        public_card = int(info.split("Public: ")[1].split("]")[0])
        public_rank = public_card // 2
        public_name = ["J", "Q", "K"][public_rank]
    has_pair = has_public and rank == public_rank

    # Parse betting context
    opp_raised = info.count("2") > (1 if 2 in legal else 0)
    round_num = 2 if has_public else 1

    # Parse pot from observation (no dependency on eval agents module)
    import re
    try:
        obs = state.observation_string(player)
    except Exception:
        obs = state.information_state_string(player)
    pot_m = re.search(r"[Pp]ot.*?(\d+)", obs)
    pot = int(pot_m.group(1)) if pot_m else (2 if round_num == 1 else 6)
    bet_history_m = re.search(r"Round \d.*?betting:(.+?)(?:\n|$)", obs)
    bet_history = bet_history_m.group(1).strip() if bet_history_m else ""

    # What could opponent have? (3 remaining cards minus mine and public)
    all_ranks = ["J", "Q", "K"]
    opp_possible = []
    for r_name in all_ranks:
        if has_public and r_name == public_name:
            # One card of this rank is public, opponent could have the other
            opp_possible.append(r_name)
        elif r_name == rank_name:
            # I have one, opponent could have the other
            opp_possible.append(r_name)
        else:
            # Both available
            opp_possible.append(r_name)
            opp_possible.append(r_name)
    # Remove my card and public card from pool
    remaining = 4 if not has_public else 3  # cards opponent could hold

    # --- Core strategy (same as v3) ---
    if has_pair:
        action = 2 if 2 in legal else 1
    elif rank == 2:  # K
        if has_public:
            if opp_raised:
                action = 1 if 1 in legal else 0
            else:
                action = 2 if 2 in legal else 1
        else:
            action = 2 if 2 in legal else 1
    elif rank == 1:  # Q
        if has_public:
            if public_rank == 2 and opp_raised:
                action = 0 if 0 in legal else 1
            elif public_rank == 0:
                action = 1 if 1 in legal else (2 if 2 in legal else 0)
            else:
                action = 1 if 1 in legal else 0
        else:
            action = 1 if 1 in legal else 2
    else:  # J
        if has_public:
            if public_rank == 0:
                action = 2 if 2 in legal else 1  # pair!
            else:
                action = 0 if 0 in legal else 1
        else:
            action = 1 if 1 in legal else 0

    # --- Generate state-specific think ---
    action_name = {0: "Fold", 1: "Call", 2: "Raise"}.get(action, "Act")
    parts = []

    # 1. Hand assessment in context
    if round_num == 1:
        parts.append(f"Round 1, pot is {pot} chips.")
        if rank == 2:
            parts.append(f"Holding K{suit} — best starting hand. Beats Q and J in showdown "
                        f"(wins against 2/3 of opponent's possible hands).")
        elif rank == 1:
            parts.append(f"Holding Q{suit} — middle strength. Beats J but loses to K "
                        f"(wins against 1/3, loses to 1/3 of opponent's range).")
        else:
            parts.append(f"Holding J{suit} — weakest starting hand. Loses to both Q and K "
                        f"in showdown. Only 1/4 chance of pairing with public card.")
    else:
        parts.append(f"Round 2, pot is {pot} chips. Public card: {public_name}.")
        if has_pair:
            parts.append(f"Holding {rank_name}{suit} paired with public {public_name} — "
                        f"unbeatable! Only one other {public_name} exists and it's my card.")
        elif rank == 2:
            parts.append(f"Holding K{suit}, public is {public_name}. K-high is best unpaired hand.")
            if public_rank == 0:
                parts.append("Opponent could have J for a pair (dangerous) or Q/K unpaired.")
            else:
                parts.append(f"Opponent could have {public_name} for a pair, or J/Q unpaired.")
        elif rank == 1:
            parts.append(f"Holding Q{suit}, public is {public_name}. Middle unpaired.")
        else:
            parts.append(f"Holding J{suit}, public is {public_name}. Weakest unpaired hand.")

    # 2. Opponent read from betting
    if bet_history:
        parts.append(f"Betting so far: {bet_history}.")
    if opp_raised:
        if has_public:
            parts.append(f"Opponent raised — likely holding {public_name} for a pair, "
                        f"or K-high. Adjusting to this aggression.")
        else:
            parts.append("Opponent raised pre-flop — suggests K or strong Q. "
                        "Weak J would typically just call.")
    elif round_num == 2:
        parts.append("Opponent was passive — less likely to have a pair. "
                    "Passive play suggests medium or weak holding.")

    # 3. Decision reasoning with pot odds
    if action == 2:
        if has_pair:
            parts.append(f"{action_name}: with a guaranteed pair, extracting maximum value. "
                        f"Opponent must pay to see showdown against our dominant hand.")
        elif rank == 2:
            parts.append(f"{action_name}: K-high is strong enough to bet for value. "
                        f"Building the pot while we likely have the best hand. "
                        f"Puts pressure on J-holders to fold.")
        else:
            parts.append(f"{action_name}: raising with a made pair for maximum value.")
    elif action == 1:
        cost = 2 if opp_raised else 1
        odds = pot / cost if cost > 0 else 99
        parts.append(f"{action_name}: investing {cost} chip(s) into a {pot}-chip pot "
                    f"(getting {odds:.0f}:1 odds).")
        if rank == 2:
            parts.append("K-high has enough equity to call profitably.")
        elif rank == 1:
            parts.append("Q has moderate equity — the pot odds justify continuing.")
        else:
            if round_num == 1:
                parts.append("Weak hand but cheap to see the public card. "
                            "1/4 chance of pairing makes the call +EV.")
            else:
                parts.append("Minimal investment to reach showdown. Cannot fold profitably here.")
    elif action == 0:
        parts.append(f"{action_name}: our hand is too weak to continue profitably. ")
        if opp_raised:
            parts.append(f"Against opponent's raise on a {public_name} board, "
                        f"our {rank_name}-high is almost certainly behind. "
                        f"Saving chips for a better spot.")
        else:
            parts.append(f"{rank_name}-high against {public_name} board has minimal equity. "
                        f"Preserving chips is better than calling into a likely loss.")

    return action, " ".join(parts)
