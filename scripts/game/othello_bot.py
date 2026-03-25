"""Othello bot v5: Rule-based strategy think + MCTS action selection.

Key insight: SFT learns IF-THEN rules, not spatial intuition.
Encode othello as deterministic rules the model can pattern-match:

Rule 1: CORNER — always take if available (corners never flip)
Rule 2: STABLE CHAIN — after corner, extend along edge (permanently stable)
Rule 3: X-SQUARE BAN — never play diagonal-to-corner if corner is empty
Rule 4: C-SQUARE CAUTION — adjacent-to-corner risky unless corner is ours
Rule 5: MOBILITY — choose move that minimizes opponent's options
Rule 6: FRONTIER — choose move that minimizes our exposed discs
Rule 7: ENDGAME — maximize disc count in final moves
"""

from mcts_helper import get_mcts_bot, mcts_step_with_stats, format_mcts_think

_CORNERS = {0, 7, 56, 63}
_CORNER_NAMES = {0: "a1", 7: "h1", 56: "a8", 63: "h8"}
_DIRS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

# X-squares: diagonal to corners
_X_SQUARES = {9: 0, 14: 7, 49: 56, 54: 63}  # x-square → adjacent corner
# C-squares: orthogonal to corners
_C_SQUARES = {1: 0, 8: 0, 6: 7, 15: 7, 48: 56, 57: 56, 55: 63, 62: 63}

# Edge positions per corner (for stable chain detection)
_CORNER_EDGES = {
    0: {"row": list(range(0, 8)), "col": list(range(0, 57, 8))},
    7: {"row": list(range(0, 8)), "col": list(range(7, 64, 8))},
    56: {"row": list(range(56, 64)), "col": list(range(0, 57, 8))},
    63: {"row": list(range(56, 64)), "col": list(range(7, 64, 8))},
}


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


def _pos_name(pos):
    return f"{'abcdefgh'[pos % 8]}{pos // 8 + 1}"


def _count_stable_chain(corner, my_discs):
    """Count stable discs in edge chains from a corner we own."""
    if corner not in my_discs:
        return 0
    stable = {corner}
    r0, c0 = corner // 8, corner % 8
    for dr, dc in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
        nr, nc = r0 + dr, c0 + dc
        while 0 <= nr < 8 and 0 <= nc < 8:
            p = nr * 8 + nc
            if p in my_discs:
                stable.add(p)
            else:
                break
            nr, nc = nr + dr, nc + dc
    return len(stable)


def _explain_move(state, player, action, legal):
    """Generate rule-based think using IF-THEN patterns."""
    my_discs, opp_discs = _parse_board(state, player)
    all_discs = my_discs | opp_discs
    empty_count = 64 - len(all_discs)
    pos = _pos_name(action)

    # After-move analysis
    child = state.child(action)
    opp = 1 - player
    child_my, child_opp = _parse_board(child, player)
    flipped = len(child_my) - len(my_discs) - 1
    opp_mob = len(child.legal_actions(opp)) if not child.is_terminal() and child.current_player() == opp else 0
    my_mob = len(legal)

    my_corners = my_discs & _CORNERS
    opp_corners = opp_discs & _CORNERS
    my_corner_names = [_CORNER_NAMES[c] for c in my_corners]
    opp_corner_names = [_CORNER_NAMES[c] for c in opp_corners]
    score = f"{len(child_my)}-{len(child_opp)}"

    # --- RULE-BASED THINK ---

    # RULE 1: CORNER
    if action in _CORNERS:
        cn = _CORNER_NAMES[action]
        # Count how many stable discs this creates
        new_stable = _count_stable_chain(action, child_my)
        parts = [f"Rule: TAKE CORNER. {cn} is available — corners can never be flipped by opponent."]
        if new_stable > 1:
            parts.append(f"This immediately creates {new_stable} permanently stable discs along the edge.")
        if opp_corner_names:
            parts.append(f"Opponent has corner(s) {', '.join(opp_corner_names)}, so securing {cn} "
                        f"is critical. Now we have {len(my_corner_names)+1} vs their {len(opp_corner_names)}.")
        else:
            parts.append(f"First corner captured — major strategic advantage. "
                        f"From {cn}, we can build stable chains along both adjacent edges.")
        parts.append(f"Flips {flipped} disc(s). Score {score}, {empty_count-1} empty.")
        return " ".join(parts)

    # RULE 2: STABLE CHAIN (extending from our corner along edge)
    if action // 8 in (0, 7) or action % 8 in (0, 7):  # edge position
        adj_corner = None
        best_chain = 0
        for corner in _CORNERS:
            if corner not in child_my:
                continue
            cr, cc = corner // 8, corner % 8
            ar, ac = action // 8, action % 8
            if cr != ar and cc != ac:
                continue  # not on same edge
            # Check if action is actually PART of the stable chain from this corner
            chain_before = _count_stable_chain(corner, child_my - {action})
            chain_after = _count_stable_chain(corner, child_my)
            if chain_after > chain_before and chain_after >= 2:
                # Action genuinely extends the chain
                if chain_after > best_chain:
                    best_chain = chain_after
                    adj_corner = corner
        if adj_corner is not None:
            cn = _CORNER_NAMES[adj_corner]
            return (f"Rule: EXTEND STABLE CHAIN. Playing {pos} extends our edge chain from corner {cn}. "
                    f"Chain grows to {best_chain} permanently stable discs — these can never be flipped. "
                    f"Stable chains from corners are the foundation of winning othello. "
                    f"Flips {flipped}. Score {score}. Opponent has {opp_mob} moves.")

    # RULE 3: X-SQUARE BAN
    if action in _X_SQUARES:
        adj_corner = _X_SQUARES[action]
        cn = _CORNER_NAMES[adj_corner]
        if adj_corner not in all_discs:
            # X-square with empty corner — normally banned, but MCTS says do it
            return (f"Rule exception: X-SQUARE {pos} near empty corner {cn}. "
                    f"Normally this is the worst square — it gives opponent corner access. "
                    f"However, deep search finds a tactical sequence that compensates: "
                    f"either we capture {cn} next, or opponent is forced elsewhere. "
                    f"Flips {flipped}. Score {score}. Opponent has {opp_mob} moves.")
        elif adj_corner in my_discs:
            return (f"Rule: SAFE X-SQUARE. {pos} is next to OUR corner {cn}, "
                    f"so this disc becomes part of our stable territory. "
                    f"X-squares are only dangerous when the adjacent corner is empty or opponent's. "
                    f"Flips {flipped}. Score {score}.")

    # RULE 4: C-SQUARE
    if action in _C_SQUARES:
        adj_corner = _C_SQUARES[action]
        cn = _CORNER_NAMES[adj_corner]
        if adj_corner in my_discs:
            return (f"Rule: SAFE C-SQUARE. {pos} next to our corner {cn} — extends stable edge. "
                    f"C-squares become permanent when we control the adjacent corner. "
                    f"Flips {flipped}. Score {score}.")
        elif adj_corner not in all_discs:
            return (f"Rule exception: C-SQUARE {pos} near empty corner {cn}. "
                    f"Risky — opponent could use this to access {cn}. "
                    f"But search confirms this is tactically necessary right now. "
                    f"Flips {flipped}. Opponent has {opp_mob} moves. Score {score}.")

    # RULE 5: MOBILITY SQUEEZE
    if opp_mob <= 3:
        # Check if opponent is forced near corners
        opp_legal = child.legal_actions(opp) if not child.is_terminal() else []
        forced_near_corner = [_pos_name(a) for a in opp_legal
                             if a in _X_SQUARES or a in _C_SQUARES]
        parts = [f"Rule: MOBILITY SQUEEZE. Playing {pos} leaves opponent with only {opp_mob} legal move(s)."]
        if forced_near_corner:
            parts.append(f"Opponent may be forced to play {', '.join(forced_near_corner)} "
                        f"(dangerous squares near corners), giving us corner access.")
        else:
            parts.append(f"With very few options, opponent is likely forced into a bad position.")
        parts.append(f"We had {my_mob} choices. Flips {flipped}. Score {score}.")
        return " ".join(parts)

    # RULE 6: FRONTIER
    my_frontier = sum(1 for d in child_my if any(
        0 <= (d // 8 + dr) < 8 and 0 <= (d % 8 + dc) < 8
        and (d // 8 + dr) * 8 + (d % 8 + dc) not in (child_my | child_opp)
        for dr, dc in _DIRS))
    opp_frontier = sum(1 for d in child_opp if any(
        0 <= (d // 8 + dr) < 8 and 0 <= (d % 8 + dc) < 8
        and (d // 8 + dr) * 8 + (d % 8 + dc) not in (child_my | child_opp)
        for dr, dc in _DIRS))

    if my_frontier < opp_frontier and my_frontier <= 6:
        return (f"Rule: MINIMIZE FRONTIER. Playing {pos} keeps our exposed discs low "
                f"({my_frontier} ours vs {opp_frontier} opponent's). "
                f"Fewer exposed discs = fewer ways for opponent to outflank us. "
                f"This is the key mid-game principle: stay compact, let opponent spread out. "
                f"Flips {flipped}. Score {score}. Opponent has {opp_mob} moves.")

    # RULE 7: DON'T BE GREEDY (mid-game, fewer discs = better)
    if empty_count > 15 and len(child_my) < len(child_opp) and flipped <= 1:
        return (f"Rule: STAY COMPACT. Playing {pos} flips only {flipped} — intentionally keeping disc count low "
                f"({len(child_my)} ours vs {len(child_opp)} opponent's). "
                f"In mid-game othello, having FEWER discs is often better: "
                f"opponent has more pieces to defend, we have fewer targets to attack. "
                f"More opponent discs = more of their frontier exposed = more moves for us. "
                f"Opponent has {opp_mob} moves. {empty_count-1} empty.")

    # RULE 8: PARITY (endgame — last move advantage)
    if empty_count <= 15 and empty_count > 2:
        # Count empty regions — player who moves last in a region wins it
        parity_good = empty_count % 2 == 1  # odd empties = we move last (if we move next)
        return (f"Rule: ENDGAME PARITY. {empty_count-1} squares left after this move. "
                f"Playing {pos} flips {flipped} → score {score}. "
                f"Parity {'favorable' if parity_good else 'unfavorable'} — "
                f"{'we get the last move' if parity_good else 'opponent gets last move'}. "
                f"In endgame, the player making the final moves in each region controls the outcome. "
                f"Every flip counts double. Opponent has {opp_mob} responses.")

    # RULE 9: FINAL MOVES
    if empty_count <= 2:
        return (f"Rule: FINAL MOVES. Only {empty_count-1} squares left. "
                f"Playing {pos} flips {flipped} → score {score}. "
                f"{'We win!' if len(child_my) > len(child_opp) else 'Need more flips to win.'}")

    # RULE 8: EDGE (non-corner, non-C/X)
    if action // 8 in (0, 7) or action % 8 in (0, 7):
        edge_name = ""
        if action // 8 == 0: edge_name = "top"
        elif action // 8 == 7: edge_name = "bottom"
        elif action % 8 == 0: edge_name = "left"
        elif action % 8 == 7: edge_name = "right"
        # Check if building toward an open corner
        nearest_corner = None
        min_dist = 99
        for c in _CORNERS:
            if c not in all_discs:
                dist = abs(c // 8 - action // 8) + abs(c % 8 - action % 8)
                if dist < min_dist:
                    min_dist = dist
                    nearest_corner = c
        parts = [f"Rule: EDGE CONTROL. Playing {pos} on the {edge_name} edge. "
                f"Edge discs can only be attacked from 5 directions (vs 8 for interior), "
                f"making them harder to flip."]
        if nearest_corner:
            parts.append(f"Building toward open corner {_CORNER_NAMES[nearest_corner]} "
                        f"({min_dist} steps away).")
        parts.append(f"Flips {flipped}. Score {score}. Opponent has {opp_mob} moves.")
        return " ".join(parts)

    # DEFAULT: interior move with flipping analysis
    if flipped >= 3:
        return (f"Rule: HIGH-IMPACT FLIP. Playing {pos} flips {flipped} opponent discs at once, "
                f"swinging the count to {score}. In othello, large flips shift board control. "
                f"Opponent has {opp_mob} responses. {empty_count-1} empty squares remain. "
                f"Corners: {len(my_corners)} ours, {len(opp_corners)} opponent's.")

    return (f"Playing {pos}: best available move from search. "
            f"Flips {flipped} disc(s) → {score}. Opponent has {opp_mob} options. "
            f"Corners: ours={', '.join(my_corner_names) or 'none'}, "
            f"theirs={', '.join(opp_corner_names) or 'none'}. "
            f"{empty_count-1} empty squares. "
            f"{'Frontier advantage' if my_frontier <= opp_frontier else 'Working to reduce frontier'}.")


def _pos_label(action):
    """Quick position type label for candidate annotation."""
    if action in _CORNERS:
        return "corner"
    if action in _X_SQUARES:
        return "X-square"
    if action in _C_SQUARES:
        return "C-square"
    r, c = action // 8, action % 8
    if r in (0, 7) or c in (0, 7):
        return "edge"
    if 2 <= r <= 5 and 2 <= c <= 5:
        return "center"
    return "inner"


def _count_flips(action, my_discs, opp_discs):
    """Count how many opponent pieces this move flips."""
    r, c = action // 8, action % 8
    total = 0
    for dr, dc in _DIRS:
        flips = 0
        nr, nc = r + dr, c + dc
        while 0 <= nr < 8 and 0 <= nc < 8:
            pos = nr * 8 + nc
            if pos in opp_discs:
                flips += 1
            elif pos in my_discs:
                total += flips
                break
            else:
                break
            nr, nc = nr + dr, nc + dc
    return total


def _frontier_count(pieces, all_occupied):
    """Count pieces adjacent to empty cells."""
    count = 0
    for p in pieces:
        r, c = p // 8, p % 8
        for dr, dc in _DIRS:
            nr, nc = r + dr, c + dc
            if 0 <= nr < 8 and 0 <= nc < 8 and (nr * 8 + nc) not in all_occupied:
                count += 1
                break
    return count


def _get_game_context(action, state, player):
    """Get game-specific context for EVERY action."""
    my, opp = _parse_board(state, player)
    name = _pos_name(action)
    r, c = action // 8, action % 8

    # Position type — objective, no good/bad labels
    if action in _CORNERS:
        pos_type = "corner (permanently stable)"
    elif action in _X_SQUARES:
        corner = _X_SQUARES[action]
        pos_type = f"X-square near corner {_CORNER_NAMES[corner]}"
    elif action in _C_SQUARES:
        pos_type = "C-square"
    elif r in (0, 7) or c in (0, 7):
        pos_type = "edge"
    elif 2 <= r <= 5 and 2 <= c <= 5:
        pos_type = "center"
    else:
        pos_type = "inner"

    # Flips — just the number
    flips = _count_flips(action, my, opp)

    # Stable chain
    stable_info = ""
    if action in _CORNERS or (r in (0, 7) or c in (0, 7)):
        my_after = my | {action}
        for corner in _CORNERS:
            s = _count_stable_chain(corner, my_after)
            if s > 1:
                stable_info = f"Stable chain {s}."
                break

    # Frontier — just the number
    my_after = my | {action}
    all_occ = my_after | opp
    frontier = _frontier_count(my_after, all_occ)

    parts = [f"Playing {name}. {pos_type}."]
    if flips > 0:
        parts.append(f"Flips {flips}.")
    if stable_info:
        parts.append(stable_info)
    parts.append(f"Frontier {frontier}.")
    return " ".join(parts)


def othello_bot(state, player):
    legal = state.legal_actions(player)
    if not legal:
        return 0, "No legal moves available, must pass."

    game = state.get_game()
    bot = get_mcts_bot(game, "othello")
    if bot is not None:
        try:
            action, stats, root = mcts_step_with_stats(bot, state)
            if action in legal and stats:
                # Annotate ALL candidates with position type
                annotated = []
                for a, name, visits, wr in stats:
                    label = _pos_label(a)
                    annotated.append((a, f"{name} [{label}]", visits, wr))
                context = _get_game_context(action, state, player)
                think = format_mcts_think(annotated, state, player, context, root)
                if think is not None:
                    return action, think
            if action in legal:
                return action, _explain_move(state, player, action, legal)
        except Exception:
            pass

    for a in legal:
        if a in _CORNERS:
            return a, f"Corner {_CORNER_NAMES[a]} available — always take corners."
    return legal[0], "Taking available move."
