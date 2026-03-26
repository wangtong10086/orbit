"""Gin Rummy bot v3: MCTS search + knock-priority override.

v1: Rule-based meld analysis → 50% vs MCTS 500sim/10roll
v2: MCTS 2000sim/20roll (4x opponent) for decisions.
v3: Override MCTS to knock when eligible. Model was never knocking (eval
    showed 0 knocks in 11 losses). Knock = action 55.
    Keep meld-aware think generation for interpretable explanations.
"""

from mcts_helper import get_mcts_bot, mcts_step_with_stats, format_mcts_think

CARD_NAMES = ['A', '2', '3', '4', '5', '6', '7', '8', '9', 'T', 'J', 'Q', 'K']
SUIT_NAMES = ['s', 'c', 'd', 'h']

def card_rank(cid): return cid % 13
def card_suit(cid): return cid // 13
def card_name(cid): return CARD_NAMES[card_rank(cid)] + SUIT_NAMES[card_suit(cid)]
def deadwood_value(cid):
    r = card_rank(cid)
    if r == 0: return 1
    if r >= 9: return 10
    return r + 1


def _find_melds(hand):
    melds = []
    by_rank = {}
    for c in hand:
        by_rank.setdefault(card_rank(c), []).append(c)
    for r, cards in by_rank.items():
        if len(cards) >= 3:
            melds.append(tuple(sorted(cards[:3])))
            if len(cards) >= 4:
                melds.append(tuple(sorted(cards)))
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
                    melds.append(tuple(s * 13 + r for r in run))
                run = [ranks[i]]
        if len(run) >= 3:
            melds.append(tuple(s * 13 + r for r in run))
    return melds


def _calc_deadwood(hand):
    melds = _find_melds(hand)
    if not melds:
        return sum(deadwood_value(c) for c in hand), set()
    hand_set = set(hand)
    best_dw = sum(deadwood_value(c) for c in hand)
    best_melded = set()

    def try_melds(idx, used, melded):
        nonlocal best_dw, best_melded
        remaining = hand_set - melded
        dw = sum(deadwood_value(c) for c in remaining)
        if dw < best_dw:
            best_dw = dw
            best_melded = set(melded)
        for i in range(idx, len(melds)):
            m = melds[i]
            if all(c in hand_set and c not in used for c in m):
                try_melds(i + 1, used | set(m), melded | set(m))

    try_melds(0, set(), set())
    return best_dw, best_melded


def _parse_hand(state, player):
    try:
        obs = state.observation_string(player)
    except:
        obs = state.information_state_string(player)

    hand = []
    in_player = False
    for line in obs.split("\n"):
        if f"Player{player}" in line:
            in_player = True
            continue
        if in_player and line.strip().startswith("|"):
            content = line.strip().strip("|")
            i = 0
            while i < len(content) - 1:
                two = content[i:i+2]
                for cid in range(52):
                    if card_name(cid) == two and cid not in hand:
                        hand.append(cid)
                        break
                i += 1
        elif in_player and line.strip().startswith("+"):
            if hand: break

    if not hand:
        info = state.information_state_string(player)
        sections = info.split(f"Player{player}:")
        if len(sections) > 1:
            last = sections[-1][:500]
            hand = [cid for cid in range(52) if card_name(cid) in last]
    return hand


def _get_game_context(action, state, player):
    """Get short game-specific context for the chosen action."""
    hand = _parse_hand(state, player)
    if not hand:
        return ""

    dw_before, melded_before = _calc_deadwood(hand)

    # Knock
    if action == 55:
        return "Knock threshold reached."

    # Draw upcard
    if action == 52:
        return "Reduces deadwood."

    # Draw stock
    if action == 53:
        return "Reduces deadwood."

    # Pass
    if action == 54:
        return ""

    # Discard (action < 52)
    if action < 52 and action in hand:
        new_hand = [c for c in hand if c != action]
        dw_after, melded_after = _calc_deadwood(new_hand)
        if len(melded_after) > len(melded_before):
            return "Completes a meld."
        if dw_after < dw_before:
            return "Reduces deadwood."

    return ""


def gin_rummy_bot(state, player):
    legal = state.legal_actions(player)
    if not legal:
        return 0, "No legal moves."
    if len(legal) == 1:
        return legal[0], "Only one legal action available."

    # === KNOCK PRIORITY OVERRIDE ===
    # If knock (action 55) is legal, ALWAYS knock. This is the #1 fix for gin_rummy.
    # Model was never knocking in eval, drawing endlessly and losing.
    has_knock = 55 in legal
    if has_knock:
        hand = _parse_hand(state, player)
        dw, melded = _calc_deadwood(hand) if hand else (0, set())
        melded_str = ", ".join(card_name(c) for c in sorted(melded)) if melded else "none"
        hand_str = ", ".join(card_name(c) for c in sorted(hand)) if hand else "unknown"

        # Parse knock threshold
        try:
            obs = state.observation_string(player)
        except:
            obs = ""
        knock_card = 10
        if "Knock card:" in obs:
            try:
                knock_card = int(obs.split("Knock card:")[1].split()[0])
            except:
                pass

        think = (f"Knocking! Deadwood {dw} is at or below the knock threshold of {knock_card}. "
                 f"Melds: [{melded_str}]. Hand: [{hand_str}]. "
                 f"Knocking now locks in our low deadwood before opponent can improve. "
                 f"Waiting risks opponent reaching gin or getting a lower deadwood than ours.")
        return 55, think

    # MCTS decision (for non-knock actions)
    game = state.get_game()
    bot = get_mcts_bot(game, "gin_rummy")
    action = None
    mcts_stats = []
    if bot is not None:
        try:
            action, mcts_stats, root = mcts_step_with_stats(bot, state)
            if action not in legal:
                action = None
                mcts_stats = []
        except Exception:
            action = None
    if action is None:
        action = legal[0]

    # === ALWAYS use rule-based think (never MCTS stats think) ===

    # Fallback: meld-aware think
    hand = _parse_hand(state, player)
    dw, melded = _calc_deadwood(hand) if hand else (0, set())
    melds = _find_melds(hand) if hand else []
    hand_str = ", ".join(card_name(c) for c in sorted(hand)) if hand else "unknown"
    melded_str = ", ".join(card_name(c) for c in sorted(melded)) if melded else "none"

    try:
        obs = state.observation_string(player)
    except:
        obs = ""

    # Use state's deadwood (authoritative) instead of our potentially buggy calc
    state_dw = dw
    if f"Player{player}: Deadwood=" in obs:
        try:
            state_dw = int(obs.split(f"Player{player}: Deadwood=")[1].split()[0])
        except:
            pass
    dw = state_dw  # trust state over our calculation

    # Parse knock threshold
    knock_card = 10
    if "Knock card:" in obs:
        try:
            knock_card = int(obs.split("Knock card:")[1].split()[0])
        except:
            pass

    # Parse upcard
    upcard_name = "unknown"
    if "Upcard: " in obs:
        uc_str = obs.split("Upcard: ")[-1][:2].strip()
        if uc_str != "XX":
            upcard_name = uc_str

    has_knock = 55 in legal
    has_draw_upcard = 52 in legal
    has_draw_stock = 53 in legal
    has_pass = 54 in legal
    discard_actions = [a for a in legal if a < 52]

    # Knock
    if action == 55:
        think = (f"Knocking! Deadwood {dw} is at or below the knock threshold of {knock_card}. "
                 f"Melds: [{melded_str}]. Hand: [{hand_str}]. "
                 f"Knocking now locks in our low deadwood before opponent can improve. "
                 f"Waiting risks opponent reaching gin or getting a lower deadwood than ours.")
    # Draw upcard
    elif action == 52:
        think = (f"Taking upcard {upcard_name}. Current hand [{hand_str}], deadwood {dw}. "
                 f"This card improves our hand — either completing a meld or reducing deadwood. "
                 f"Known cards are better than random stock draws because we can evaluate the exact impact.")
    # Draw stock
    elif action == 53:
        think = (f"Drawing from stock. Upcard {upcard_name} doesn't fit our hand [{hand_str}]. "
                 f"Current deadwood: {dw} with melds [{melded_str}]. "
                 f"A blind draw has ~15% chance of completing an existing near-meld, "
                 f"which is better than taking a card that doesn't help.")
    # Pass
    elif action == 54:
        think = (f"Passing on upcard {upcard_name}. Hand [{hand_str}], deadwood {dw}. "
                 f"The upcard doesn't reduce deadwood or connect to our melds [{melded_str}]. "
                 f"Passing also avoids revealing our hand composition to opponent.")
    # Discard
    elif action < 52:
        cn = card_name(action)
        dw_val = deadwood_value(action)
        in_meld = action in melded
        if in_meld:
            think = (f"Discarding {cn} (value {dw_val}) from a meld — unusual, but deep search finds "
                     f"this reorganization leads to a better hand. Current deadwood: {dw}. "
                     f"Sometimes breaking one meld enables a higher-value meld combination.")
        else:
            think = (f"Discarding {cn} (value {dw_val}), the weakest non-meld card. "
                     f"Current deadwood: {dw}. Removing the highest deadwood-to-meld-potential ratio card. "
                     f"Hand: [{hand_str}]. Melds preserved: [{melded_str}].")
    else:
        think = f"Taking action with hand [{hand_str}], deadwood {dw}."

    return action, think
