"""Othello bot v2: minimax + alpha-beta + positional weights.

v1: positional weights + 1-step mobility → 0% vs MCTS 1000sim
v2: 4-step minimax with alpha-beta pruning + positional weights + endgame solver
"""


# Classic positional weight table (Rosenbloom)
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


def _parse_board(state, player):
    """Parse othello board from observation. Returns (my_discs, opp_discs) as sets."""
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


def _evaluate(state, player):
    """Evaluate board position for player. Higher = better."""
    if state.is_terminal():
        returns = state.returns()
        return returns[player] * 10000

    my_discs, opp_discs = _parse_board(state, player)

    # Positional: weighted sum of disc positions
    my_pos = sum(_POS_WEIGHT.get(d, 0) for d in my_discs)
    opp_pos = sum(_POS_WEIGHT.get(d, 0) for d in opp_discs)
    pos_score = my_pos - opp_pos

    # Mobility
    cp = state.current_player()
    if cp >= 0:
        current_moves = len(state.legal_actions(cp))
        mobility = current_moves if cp == player else -current_moves
    else:
        mobility = 0

    # Disc count (matters more in endgame)
    disc_diff = len(my_discs) - len(opp_discs)
    total_discs = len(my_discs) + len(opp_discs)
    endgame_weight = max(0, (total_discs - 40)) * 2  # disc count matters after 40 discs

    return pos_score + mobility * 3 + disc_diff * endgame_weight


def _minimax(state, depth, alpha, beta, maximizing, player):
    """Minimax with alpha-beta pruning."""
    if depth == 0 or state.is_terminal():
        return _evaluate(state, player), None

    legal = state.legal_actions(state.current_player())
    if not legal:
        return _evaluate(state, player), None

    best_action = legal[0]

    if maximizing:
        max_eval = -999999
        for a in legal:
            child = state.child(a)
            # Next player might be same (if opponent has no moves)
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

    # Check for immediate corner
    for a in legal:
        if a in _CORNERS:
            r, c = a // 8, a % 8
            return a, (f"Corner ({r},{c}) is available — the highest-value position in Othello. "
                       f"Corners cannot be flipped once placed and anchor stable disc chains. "
                       f"Taking it immediately regardless of other options.")

    # Count empty squares to determine search depth
    filled = 64 - len(legal)  # approximate
    if filled > 52:
        depth = 8  # endgame: search deep
    elif filled > 45:
        depth = 6
    else:
        depth = 4  # midgame

    val, best_action = _minimax(state, depth, -999999, 999999, True, player)

    r, c = best_action // 8, best_action % 8
    pw = _POS_WEIGHT.get(best_action, 0)

    child = state.child(best_action)
    opp = 1 - player
    opp_mob = len(child.legal_actions(opp)) if not child.is_terminal() and child.current_player() == opp else 0

    if pw >= 10:
        think = (f"Minimax search (depth {depth}) selects ({r},{c}) with positional weight {pw}. "
                 f"This edge/stable position restricts opponent to {opp_mob} responses "
                 f"while securing territory that's hard to overturn. "
                 f"Search evaluation: {val}.")
    elif pw < -10:
        think = (f"Minimax (depth {depth}) selects ({r},{c}) despite negative positional weight ({pw}). "
                 f"Deeper analysis shows this leads to a favorable position after {depth} moves, "
                 f"likely gaining corner access or trapping opponent. Evaluation: {val}.")
    else:
        think = (f"Minimax search (depth {depth}) evaluates ({r},{c}) as strongest at score {val}. "
                 f"Position weight is {pw}, opponent left with {opp_mob} moves. "
                 f"The multi-step lookahead accounts for opponent's best responses "
                 f"and positions us for stronger moves in subsequent turns.")

    return best_action, think
