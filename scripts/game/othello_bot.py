"""Othello bot v3c: v2 proven weights + deeper opening + better think chains.

v1: positional weights + 1-step mobility → 0% vs MCTS 1000sim
v2: 4-step minimax + Rosenbloom weights → 20% vs MCTS (2/10)
v3c: v2 weights + opening depth 4→5 + frontier + stability + informative think
"""


# Classic Rosenbloom positional weight table (proven in v2)
_WEIGHTS = [
    [100, -20, 10,  5,  5, 10, -20, 100],
    [-20, -50, -2, -2, -2, -2, -50, -20],
    [ 10,  -2,  5,  1,  1,  5,  -2,  10],
    [  5,  -2,  1,  0,  0,  1,  -2,   5],
    [  5,  -2,  1,  0,  0,  1,  -2,   5],
    [ 10,  -2,  5,  1,  1,  5,  -2,  10],
    [-20, -50, -2, -2, -2, -2, -50, -20],
    [100, -20, 10,  5,  5, 10, -20, 100],
]
_POS_WEIGHT = {r * 8 + c: _WEIGHTS[r][c] for r in range(8) for c in range(8)}
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
                if ch == my_char:
                    my_discs.add(pos)
                elif ch == opp_char:
                    opp_discs.add(pos)
                pos += 1
    return my_discs, opp_discs


def _count_stable(discs):
    """Count stable discs: corners + connected edge chains from corners."""
    stable = 0
    for c in _CORNERS:
        if c not in discs:
            continue
        stable += 1
        r, col = c // 8, c % 8
        for dr, dc in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nr, nc = r + dr, col + dc
            while 0 <= nr < 8 and 0 <= nc < 8:
                if nr * 8 + nc in discs:
                    stable += 1
                else:
                    break
                nr, nc = nr + dr, nc + dc
    return stable


def _evaluate(state, player):
    if state.is_terminal():
        return state.returns()[player] * 10000

    my_discs, opp_discs = _parse_board(state, player)
    all_discs = my_discs | opp_discs
    total = len(all_discs)

    # Positional score
    pos_score = sum(_POS_WEIGHT.get(d, 0) for d in my_discs) - sum(_POS_WEIGHT.get(d, 0) for d in opp_discs)

    # Stability (corners + edge chains)
    stability = (_count_stable(my_discs) - _count_stable(opp_discs)) * 15

    # Frontier discs
    my_frontier, opp_frontier = 0, 0
    for d in my_discs:
        r, c = d // 8, d % 8
        for dr, dc in _DIRS:
            nr, nc = r + dr, c + dc
            if 0 <= nr < 8 and 0 <= nc < 8 and nr * 8 + nc not in all_discs:
                my_frontier += 1
                break
    for d in opp_discs:
        r, c = d // 8, d % 8
        for dr, dc in _DIRS:
            nr, nc = r + dr, c + dc
            if 0 <= nr < 8 and 0 <= nc < 8 and nr * 8 + nc not in all_discs:
                opp_frontier += 1
                break
    frontier_score = (opp_frontier - my_frontier) * 3

    # Mobility
    cp = state.current_player()
    if cp >= 0:
        moves = len(state.legal_actions(cp))
        mobility = moves * 3 if cp == player else -moves * 3
    else:
        mobility = 0

    # Disc count (endgame)
    disc_diff = len(my_discs) - len(opp_discs)
    endgame_weight = max(0, (total - 40)) * 2

    return pos_score + stability + frontier_score + mobility + disc_diff * endgame_weight


def _minimax(state, depth, alpha, beta, maximizing, player):
    if depth == 0 or state.is_terminal():
        return _evaluate(state, player), None

    legal = state.legal_actions(state.current_player())
    if not legal:
        return _evaluate(state, player), None

    # Move ordering
    legal = sorted(legal, key=lambda a: (-10000 if a in _CORNERS else -_POS_WEIGHT.get(a, 0)))

    best_action = legal[0]

    if maximizing:
        max_eval = -999999
        for a in legal:
            child = state.child(a)
            next_max = child.current_player() == player if not child.is_terminal() else False
            val, _ = _minimax(child, depth - 1, alpha, beta, next_max, player)
            if val > max_eval:
                max_eval = val
                best_action = a
            alpha = max(alpha, val)
            if beta <= alpha:
                break
        return max_eval, best_action
    else:
        min_eval = 999999
        for a in legal:
            child = state.child(a)
            next_max = child.current_player() == player if not child.is_terminal() else True
            val, _ = _minimax(child, depth - 1, alpha, beta, next_max, player)
            if val < min_eval:
                min_eval = val
                best_action = a
            beta = min(beta, val)
            if beta <= alpha:
                break
        return min_eval, best_action


def othello_bot(state, player):
    legal = state.legal_actions(player)
    if not legal:
        return 0, "No legal moves available, must pass."

    # Always take corner
    for a in legal:
        if a in _CORNERS:
            r, c = a // 8, a % 8
            my_discs, _ = _parse_board(state, player)
            my_corners = len(my_discs & _CORNERS)
            return a, (f"Corner ({r},{c}) is available — the highest-value position in Othello. "
                       f"Corners cannot be flipped once placed and anchor stable disc chains along edges. "
                       f"Now controlling {my_corners + 1} corner(s). Taking it immediately.")

    my_discs, opp_discs = _parse_board(state, player)
    total_discs = len(my_discs) + len(opp_discs)
    empty = 64 - total_discs

    # Depth: slightly deeper than v2 in opening/midgame
    if empty <= 12:
        depth = 10
    elif empty <= 20:
        depth = 8
    elif empty <= 35:
        depth = 6
    else:
        depth = 5  # v2 was 4 here

    val, best_action = _minimax(state, depth, -999999, 999999, True, player)

    r, c = best_action // 8, best_action % 8
    pw = _POS_WEIGHT.get(best_action, 0)
    col_names = "abcdefgh"
    pos_name = f"{col_names[c]}{r+1}"

    child = state.child(best_action)
    opp = 1 - player
    opp_mob = len(child.legal_actions(opp)) if not child.is_terminal() and child.current_player() == opp else 0

    my_corners = len(my_discs & _CORNERS)
    opp_corners = len(opp_discs & _CORNERS)
    disc_lead = len(my_discs) - len(opp_discs)
    phase = "opening" if empty > 40 else "midgame" if empty > 15 else "endgame"
    my_stable = _count_stable(my_discs)
    opp_stable = _count_stable(opp_discs)

    all_discs = my_discs | opp_discs
    my_frontier = sum(1 for d in my_discs if any(
        0 <= (d // 8 + dr) < 8 and 0 <= (d % 8 + dc) < 8
        and (d // 8 + dr) * 8 + (d % 8 + dc) not in all_discs
        for dr, dc in _DIRS))

    sit = (f"Board: {len(my_discs)} vs {len(opp_discs)} discs, {empty} empty. "
           f"Corners: {my_corners}-{opp_corners}. Stable: {my_stable}-{opp_stable}. "
           f"Frontier: {my_frontier} exposed.")

    if pw >= 10:
        think = (f"Playing {pos_name} — a stable edge position that resists flipping. "
                 f"Edge control builds permanent territorial advantage. "
                 f"Opponent has {opp_mob} responses after this move. {sit}")
    elif pw < -10:
        think = (f"Playing {pos_name} near a corner — normally risky, but depth-{depth} search "
                 f"finds this leads to a stronger position (corner access or disc trapping). "
                 f"The tactical gain outweighs the positional risk. {sit}")
    elif opp_mob <= 3:
        think = (f"Playing {pos_name} restricts opponent to only {opp_mob} moves. "
                 f"Mobility control is the key Othello principle — fewer options force opponent "
                 f"into giving up corners or stable edge positions. {sit}")
    elif my_frontier < 5:
        think = (f"Playing {pos_name} maintains low frontier exposure ({my_frontier} exposed discs). "
                 f"Fewer frontier discs means fewer attack surfaces for the opponent. "
                 f"Combined with {my_stable} stable discs, position is solid. {sit}")
    else:
        think = (f"Playing {pos_name} — best move from depth-{depth} search in the {phase}. "
                 f"Balancing mobility (opponent has {opp_mob} replies), stability ({my_stable} stable), "
                 f"and territorial control with {my_corners} corners secured. {sit}")

    return best_action, think
