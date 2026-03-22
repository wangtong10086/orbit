"""Othello bot v4: MCTS search (3000 sim) + rule-based think explanation.

v1-v3c: minimax only → 20% vs MCTS 1000sim
v4: Use our own MCTS (3000 sim) to find the best move, then use positional
    knowledge to generate an interpretable think block explaining WHY.
    MCTS finds the winning move. Rules explain the reasoning.
"""

from mcts_helper import get_mcts_bot

_CORNERS = {0, 7, 56, 63}
_DIRS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def _parse_board(state, player):
    obs = state.observation_string(player)
    my_char = 'x' if player == 0 else 'o'
    opp_char = 'o' if player == 0 else 'x'
    my_discs, opp_discs = set(), set()
    pos = 0
    for line in obs.split('\n'):
        for ch in line:
            if ch in ('x', 'o', '-'):
                if ch == my_char: my_discs.add(pos)
                elif ch == opp_char: opp_discs.add(pos)
                pos += 1
    return my_discs, opp_discs


def _count_stable(discs):
    stable = 0
    for c in _CORNERS:
        if c not in discs: continue
        stable += 1
        r, col = c // 8, c % 8
        for dr, dc in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nr, nc = r + dr, col + dc
            while 0 <= nr < 8 and 0 <= nc < 8:
                if nr * 8 + nc in discs: stable += 1
                else: break
                nr, nc = nr + dr, nc + dc
    return stable


def _explain_move(state, player, action, legal):
    """Generate state-specific think that teaches Othello decision-making.

    Every think must reference UNIQUE aspects of the current board state:
    - Specific disc positions, not just counts
    - Which corners/edges are contested RIGHT NOW
    - How this move changes the specific tactical situation
    - Comparison with alternative moves considered
    """
    my_discs, opp_discs = _parse_board(state, player)
    all_discs = my_discs | opp_discs
    empty_count = 64 - len(all_discs)
    r, c = action // 8, action % 8
    col_names = "abcdefgh"
    pos_name = f"{col_names[c]}{r+1}"
    phase = "opening" if empty_count > 40 else "midgame" if empty_count > 15 else "endgame"

    my_corners = my_discs & _CORNERS
    opp_corners = opp_discs & _CORNERS
    my_stable = _count_stable(my_discs)
    opp_stable = _count_stable(opp_discs)
    corner_names = {0: "a1", 7: "h1", 56: "a8", 63: "h8"}

    # Frontier analysis
    my_frontier = sum(1 for d in my_discs if any(
        0 <= (d // 8 + dr) < 8 and 0 <= (d % 8 + dc) < 8
        and (d // 8 + dr) * 8 + (d % 8 + dc) not in all_discs
        for dr, dc in _DIRS))
    opp_frontier = sum(1 for d in opp_discs if any(
        0 <= (d // 8 + dr) < 8 and 0 <= (d % 8 + dc) < 8
        and (d // 8 + dr) * 8 + (d % 8 + dc) not in all_discs
        for dr, dc in _DIRS))

    # After-move analysis
    child = state.child(action)
    opp = 1 - player
    opp_mob = len(child.legal_actions(opp)) if not child.is_terminal() and child.current_player() == opp else 0
    my_mob = len(legal)

    # Flipped discs
    child_my, child_opp = _parse_board(child, player)
    flipped = len(child_my) - len(my_discs) - 1

    new_my_stable = _count_stable(child_my)
    new_score = f"{len(child_my)}-{len(child_opp)}"
    old_score = f"{len(my_discs)}-{len(opp_discs)}"

    # Identify which specific corners are open, ours, theirs
    open_corners = [corner_names[c] for c in _CORNERS if c not in all_discs]
    our_corner_names = [corner_names[c] for c in my_corners]
    their_corner_names = [corner_names[c] for c in opp_corners]

    # Identify contested regions (empty corners with adjacent pieces)
    _X_SQ = {9, 14, 49, 54}
    _C_SQ = {1, 8, 6, 15, 48, 57, 55, 62}
    _CORNER_ADJ = {0: {1, 8, 9}, 7: {6, 14, 15}, 56: {48, 49, 57}, 63: {54, 55, 62}}

    # What's special about nearby area
    adj_to_action = []
    for dr, dc in _DIRS:
        nr, nc = r + dr, c + dc
        if 0 <= nr < 8 and 0 <= nc < 8:
            pos = nr * 8 + nc
            if pos in my_discs:
                adj_to_action.append(("ours", f"{col_names[nc]}{nr+1}"))
            elif pos in opp_discs:
                adj_to_action.append(("theirs", f"{col_names[nc]}{nr+1}"))

    our_adj = [name for tag, name in adj_to_action if tag == "ours"]
    their_adj = [name for tag, name in adj_to_action if tag == "theirs"]

    # Build context-specific reasoning
    parts = []

    # Part 1: What we're doing and immediate effect
    if action in _CORNERS:
        cn = corner_names[action]
        # WHY is this corner available now?
        nearby_ours = [name for tag, name in adj_to_action if tag == "ours"]
        parts.append(f"Capturing corner {cn} — the strongest possible move.")
        if nearby_ours:
            parts.append(f"Our discs at {', '.join(nearby_ours)} now become permanently stable along the edge.")
        if their_corner_names:
            parts.append(f"Opponent holds corner(s) {', '.join(their_corner_names)}, "
                        f"so securing {cn} is critical to balance the corner fight.")
        elif len(our_corner_names) > 0:
            parts.append(f"Combined with our existing corner(s) {', '.join(our_corner_names)}, "
                        f"we now dominate {len(our_corner_names)+1}/4 corners.")
        parts.append(f"This flips {flipped} disc(s), changing the score from {old_score} to {new_score}. "
                    f"{new_my_stable} of our discs are now permanently stable.")
    elif r in (0, 7) or c in (0, 7):
        # Edge move — explain which edge and why
        edge_desc = f"row {'1' if r == 0 else '8'}" if r in (0, 7) else f"column {'a' if c == 0 else 'h'}"
        parts.append(f"Playing {pos_name} on {edge_desc}.")
        if our_adj:
            parts.append(f"This connects to our disc(s) at {', '.join(our_adj)}, "
                        f"extending our edge chain.")
        # Check if near an open corner
        for corner, adj_set in _CORNER_ADJ.items():
            if action in adj_set or any(n * 8 + m == action for n in range(8) for m in range(8)
                                       if abs(n - corner // 8) <= 1 and abs(m - corner % 8) <= 1):
                if corner not in all_discs:
                    parts.append(f"This is near the open corner {corner_names[corner]} — "
                                f"building toward capturing it.")
                    break
        parts.append(f"Flipping {flipped} disc(s) → {new_score}. "
                    f"Opponent has {opp_mob} responses.")
    else:
        # Interior move
        parts.append(f"Playing {pos_name} in the interior.")
        if their_adj:
            parts.append(f"This captures into opponent's cluster around {', '.join(their_adj[:3])}, "
                        f"flipping {flipped} of their disc(s).")
        elif our_adj:
            parts.append(f"Extending from our position at {', '.join(our_adj[:3])}. "
                        f"Flips {flipped} disc(s).")

    # Part 2: Strategic reasoning (WHY this is the best)
    if opp_mob <= 3:
        forced_bad = []
        for corner, adj_set in _CORNER_ADJ.items():
            if corner not in all_discs:
                child_legal = child.legal_actions(opp) if not child.is_terminal() else []
                if any(a in adj_set for a in child_legal):
                    forced_bad.append(corner_names[corner])
        if forced_bad:
            parts.append(f"This leaves opponent with only {opp_mob} move(s), potentially forcing them "
                        f"near corner(s) {', '.join(forced_bad)} — giving us corner access next turn.")
        else:
            parts.append(f"Opponent squeezed to {opp_mob} move(s). "
                        f"Limited options often lead to forced bad positions.")
    elif my_frontier < opp_frontier:
        parts.append(f"This keeps our frontier low ({my_frontier} exposed discs vs opponent's {opp_frontier}). "
                    f"Fewer exposed discs = fewer ways for opponent to outflank us.")
    elif flipped >= 3:
        parts.append(f"A high-impact move flipping {flipped} discs, shifting the score to {new_score}.")
    elif phase == "endgame":
        parts.append(f"In the endgame with {empty_count-1} squares left, maximizing disc count is key. "
                    f"Score swings to {new_score}.")
    else:
        mob_change = f"Mobility: {my_mob} (ours) → opponent gets {opp_mob}"
        parts.append(f"{mob_change}. "
                    f"Frontier: {my_frontier} ours vs {opp_frontier} opponent's exposed discs.")

    # Part 3: Board summary with specifics
    corner_status = []
    if our_corner_names:
        corner_status.append(f"ours: {', '.join(our_corner_names)}")
    if their_corner_names:
        corner_status.append(f"opponent: {', '.join(their_corner_names)}")
    if open_corners:
        corner_status.append(f"open: {', '.join(open_corners)}")
    corners_str = "; ".join(corner_status) if corner_status else "all open"

    parts.append(f"Corners [{corners_str}]. "
                f"Stable: {new_my_stable} ours vs {opp_stable} theirs.")

    return " ".join(parts)


def othello_bot(state, player):
    legal = state.legal_actions(player)
    if not legal:
        return 0, "No legal moves available, must pass."

    # Try MCTS search first
    game = state.get_game()
    bot = get_mcts_bot(game, "othello")
    if bot is not None:
        try:
            action = bot.step(state)
            if action in legal:
                think = _explain_move(state, player, action, legal)
                return action, think
        except Exception:
            pass

    # Fallback: take corner if available
    for a in legal:
        if a in _CORNERS:
            r, c = a // 8, a % 8
            return a, f"Corner ({r},{c}) available — taking immediately as the strongest position."

    # Fallback: pick first legal
    return legal[0], "Taking available move."
