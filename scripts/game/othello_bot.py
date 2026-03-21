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

    # Stable discs: corners + connected edge chains (can never be flipped)
    def count_stable(discs):
        stable = 0
        for c in _CORNERS:
            if c in discs:
                stable += 1
                # Check edge chains from corner
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

    my_stable = count_stable(my_discs)
    opp_stable = count_stable(opp_discs)
    stability = (my_stable - opp_stable) * 15

    # Frontier discs (discs adjacent to empty = vulnerable)
    all_discs = my_discs | opp_discs
    empty = set(range(64)) - all_discs
    def frontier_count(discs):
        count = 0
        for d in discs:
            r, c = d // 8, d % 8
            for dr in [-1, 0, 1]:
                for dc in [-1, 0, 1]:
                    if dr == 0 and dc == 0: continue
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < 8 and 0 <= nc < 8 and nr * 8 + nc in empty:
                        count += 1
                        break
        return count

    my_frontier = frontier_count(my_discs)
    opp_frontier = frontier_count(opp_discs)
    frontier_score = (opp_frontier - my_frontier) * 3  # fewer frontier = better

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

    return pos_score + stability + frontier_score + mobility * 3 + disc_diff * endgame_weight


def _minimax(state, depth, alpha, beta, maximizing, player):
    """Minimax with alpha-beta pruning."""
    if depth == 0 or state.is_terminal():
        return _evaluate(state, player), None

    legal = state.legal_actions(state.current_player())
    if not legal:
        return _evaluate(state, player), None

    # Move ordering: corners first, then edges, then center (better pruning)
    def move_priority(a):
        if a in _CORNERS: return -1000
        return -_POS_WEIGHT.get(a, 0)
    legal = sorted(legal, key=move_priority)

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

    # Dynamic depth based on game phase
    # Parse board to count total discs
    my_discs, opp_discs = _parse_board(state, player)
    total_discs = len(my_discs) + len(opp_discs)
    empty = 64 - total_discs

    if empty <= 12:
        depth = 10  # endgame: solve precisely
    elif empty <= 20:
        depth = 8
    elif empty <= 35:
        depth = 6
    else:
        depth = 4  # opening

    val, best_action = _minimax(state, depth, -999999, 999999, True, player)

    r, c = best_action // 8, best_action % 8
    pw = _POS_WEIGHT.get(best_action, 0)
    col_names = "abcdefgh"
    pos_name = f"{col_names[c]}{r+1}"

    child = state.child(best_action)
    opp = 1 - player
    opp_mob = len(child.legal_actions(opp)) if not child.is_terminal() and child.current_player() == opp else 0

    # Count my corners and edges
    my_corners = len(my_discs & _CORNERS)
    disc_lead = len(my_discs) - len(opp_discs)
    phase = "opening" if empty > 40 else "midgame" if empty > 15 else "endgame"

    if best_action in _CORNERS:
        think = (f"Corner {pos_name} is available — the strongest possible move in Othello. "
                 f"Corners can never be flipped and serve as permanent anchors for stable disc chains. "
                 f"With {my_corners} corners already secured, taking this one further dominates the board edges.")
    elif pw >= 10:
        think = (f"Playing {pos_name} secures a stable edge position. In the {phase} with {empty} empty squares, "
                 f"edge control is valuable because these discs are difficult for opponent to flip. "
                 f"This move also limits opponent to {opp_mob} legal responses, reducing their options.")
    elif pw < -10:
        think = (f"Playing {pos_name} is a calculated risk — this square near a corner is usually dangerous, "
                 f"but looking {depth} moves ahead, it leads to a stronger position. "
                 f"The sacrifice of a risky square now sets up corner access or traps opponent's discs later. "
                 f"{'Leading' if disc_lead > 0 else 'Trailing'} by {abs(disc_lead)} discs in the {phase}.")
    else:
        if opp_mob <= 3:
            think = (f"Playing {pos_name} squeezes opponent down to only {opp_mob} legal moves. "
                     f"In Othello, restricting opponent's mobility is often more important than raw disc count. "
                     f"With fewer options, opponent is more likely to be forced into giving up corners or edges. "
                     f"{'Leading' if disc_lead > 0 else 'Trailing'} by {abs(disc_lead)} discs, {empty} squares remain.")
        else:
            think = (f"Playing {pos_name} in the {phase} ({empty} empty squares). "
                     f"This central position balances disc flipping with mobility — "
                     f"opponent retains {opp_mob} responses but our position improves after deeper analysis. "
                     f"Currently {'ahead' if disc_lead > 0 else 'behind'} by {abs(disc_lead)} discs with {my_corners} corners.")

    return best_action, think
