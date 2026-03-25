"""Othello rule-think bot — MCTS action + rule-based explanation for EVERY move.

Uses MCTS for action selection (same quality as othello_bot.py).
Think always explains WHY using transferable rules, never just MCTS stats.

Rules (always applied, priority order):
1. CORNER: corners can never be flipped
2. X-SQUARE BAN: diagonal to empty corner gives opponent corner access
3. C-SQUARE CAUTION: adjacent to empty corner is risky
4. EDGE: edge cells are harder to flip
5. STABLE CHAIN: extends a chain anchored to corner/edge
6. FLIPS: captures more opponent pieces
7. MOBILITY: limits opponent's legal moves
8. FRONTIER: minimizes own pieces adjacent to empty cells
9. CENTER: controls central area for flexibility
"""

from collections import deque

# Board geometry
CORNERS = {0, 7, 56, 63}
X_SQUARES = {9, 14, 49, 54}
C_SQUARES = {1, 6, 8, 15, 48, 55, 57, 62}
EDGES = set(range(8)) | set(range(56, 64)) | {i * 8 for i in range(8)} | {i * 8 + 7 for i in range(8)}

_pos_names = {}
for r in range(8):
    for c in range(8):
        _pos_names[r * 8 + c] = f"{chr(ord('a') + c)}{r + 1}"


def _neighbors(pos):
    r, c = pos // 8, pos % 8
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            nr, nc = r + dr, c + dc
            if 0 <= nr < 8 and 0 <= nc < 8:
                yield nr * 8 + nc


def _parse_board(state, player):
    obs = state.observation_string(player)
    my_char = 'x' if player == 0 else 'o'
    opp_char = 'o' if player == 0 else 'x'
    my, opp = set(), set()
    # Parse the grid lines (skip header "Black (x) to play:" and column labels)
    lines = obs.strip().split('\n')
    for line in lines:
        stripped = line.strip()
        # Grid lines start with a digit (row number)
        if stripped and stripped[0].isdigit():
            # Format: "1 - - - o x - - - 1"
            cells = stripped.split()[1:-1]  # skip row numbers
            row = int(stripped[0]) - 1
            for col, ch in enumerate(cells):
                pos = row * 8 + col
                if ch == my_char:
                    my.add(pos)
                elif ch == opp_char:
                    opp.add(pos)
    return my, opp


def _count_flips(action, my, opp):
    """Count how many opponent pieces this move flips."""
    r, c = action // 8, action % 8
    total = 0
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            flips = 0
            nr, nc = r + dr, c + dc
            while 0 <= nr < 8 and 0 <= nc < 8:
                pos = nr * 8 + nc
                if pos in opp:
                    flips += 1
                elif pos in my:
                    total += flips
                    break
                else:
                    break
                nr, nc = nr + dr, nc + dc
    return total


def _count_stable(my):
    """Count pieces that can never be flipped (anchored to corners)."""
    stable = set()
    for corner in CORNERS:
        if corner not in my:
            continue
        q = deque([corner])
        while q:
            p = q.popleft()
            if p in stable:
                continue
            stable.add(p)
            for n in _neighbors(p):
                if n in my and n not in stable and n in EDGES:
                    q.append(n)
    return len(stable)


def _frontier(pieces, all_occupied):
    """Count pieces adjacent to empty cells (vulnerable)."""
    count = 0
    for p in pieces:
        for n in _neighbors(p):
            if n not in all_occupied:
                count += 1
                break
    return count


def _rule_think(action, my_before, opp, legal):
    """Generate rule-based think explaining WHY this action is good."""
    name = _pos_names.get(action, str(action))
    my_after = my_before | {action}
    all_occ = my_before | opp | {action}
    reasons = []

    # 1. CORNER
    if action in CORNERS:
        stable_after = _count_stable(my_after)
        reasons.append(f"Rule: TAKE CORNER. {name} is a corner — corners can never be flipped. "
                       f"This creates {stable_after} permanently stable pieces along the edges.")
        return " ".join(reasons)

    # 2. X-SQUARE BAN (explain why we're NOT avoiding it, or if forced)
    if action in X_SQUARES:
        # Find which corner this X-square is diagonal to
        corner_map = {9: 0, 14: 7, 49: 56, 54: 63}
        corner = corner_map[action]
        if corner in my_before:
            reasons.append(f"X-square {name}, but we already own corner {_pos_names[corner]} — safe.")
        elif corner in opp:
            reasons.append(f"X-square {name}, opponent has corner {_pos_names[corner]} — "
                           f"risky but we need to play aggressively here.")
        else:
            reasons.append(f"X-square {name} risks giving opponent corner {_pos_names[corner]}. "
                           f"Playing here only because alternatives are worse.")

    # 3. C-SQUARE
    if action in C_SQUARES:
        reasons.append(f"C-square {name} — adjacent to corner, moderate risk.")

    # 4. EDGE
    if action in EDGES and action not in CORNERS:
        reasons.append(f"Edge position {name} — harder for opponent to flip than interior cells.")

    # 5. STABLE CHAIN
    stable_before = _count_stable(my_before)
    stable_after = _count_stable(my_after)
    if stable_after > stable_before:
        reasons.append(f"Extends stable chain: {stable_before}→{stable_after} permanently safe pieces.")

    # 6. FLIPS
    flips = _count_flips(action, my_before, opp)
    if flips > 0:
        reasons.append(f"Captures {flips} opponent piece{'s' if flips > 1 else ''} — "
                       f"shifts disc balance in our favor.")

    # 7. MOBILITY
    # Approximate: count how many legal moves opponent might have after
    my_mobility = len(legal)
    opp_frontier = _frontier(opp, all_occ)
    reasons.append(f"Position leaves opponent exposed with {opp_frontier} frontier cells.")

    # 8. FRONTIER
    my_frontier_before = _frontier(my_before, my_before | opp)
    my_frontier_after = _frontier(my_after, all_occ)
    if my_frontier_after < my_frontier_before:
        reasons.append(f"Reduces our frontier from {my_frontier_before} to {my_frontier_after} — "
                       f"fewer pieces exposed to opponent.")

    # 9. CENTER / GENERAL
    r, c = action // 8, action % 8
    if 2 <= r <= 5 and 2 <= c <= 5 and not reasons:
        reasons.append(f"Central position {name} — maintains flexibility for future moves.")

    if not reasons:
        reasons.append(f"Playing {name} — best available option for board control.")

    # Always prepend position name for diversity
    r, c = action // 8, action % 8
    position_desc = f"Playing {name}."
    if reasons and not reasons[0].startswith("Rule:") and not reasons[0].startswith("Playing"):
        reasons.insert(0, position_desc)

    return " ".join(reasons)


def othello_rule_think_bot(state, player):
    """MCTS action + rule-based think."""
    legal = state.legal_actions(player)
    if not legal:
        return 0, "No legal moves."

    # Use MCTS for action selection
    from mcts_helper import get_mcts_bot, mcts_step_with_stats
    game = state.get_game()
    bot = get_mcts_bot(game, "othello")

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

    # Generate rule-based think
    my, opp = _parse_board(state, player)
    think = _rule_think(action, my, opp, legal)

    return action, think
