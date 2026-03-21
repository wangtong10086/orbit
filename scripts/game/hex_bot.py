"""Hex bot v5: minimax + BFS path evaluation.

v1-v4: BFS path only → 0% vs MCTS
v5: Add minimax search (like othello's success) with BFS-based evaluation.
    Eval = my_path_cost - opp_path_cost (lower path cost = closer to winning).
"""

from collections import deque


def _make_board_utils(board_size):
    """Create board utility functions."""
    def rc(pos):
        return pos // board_size, pos % board_size

    def neighbors(pos):
        r, c = rc(pos)
        nbrs = []
        for dr, dc in [(-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < board_size and 0 <= nc < board_size:
                nbrs.append(nr * board_size + nc)
        return nbrs

    return rc, neighbors


def _shortest_path(board_size, empty_set, player_stones, player, neighbors_fn):
    """BFS: min empty cells to connect player's edges."""
    if player == 0:  # top-bottom
        sources = [p for p in range(board_size) if p in player_stones or p in empty_set]
        targets = set(range(board_size * (board_size - 1), board_size * board_size))
    else:  # left-right
        sources = [p for p in range(0, board_size * board_size, board_size) if p in player_stones or p in empty_set]
        targets = set(range(board_size - 1, board_size * board_size, board_size))

    dist = {}
    q = deque()
    for s in sources:
        cost = 0 if s in player_stones else 1
        if cost < dist.get(s, 999):
            dist[s] = cost
            q.append((s, cost))

    while q:
        pos, cost = q.popleft()
        if cost > dist.get(pos, 999):
            continue
        if pos in targets:
            return cost
        for n in neighbors_fn(pos):
            if n in player_stones:
                nc = cost
            elif n in empty_set:
                nc = cost + 1
            else:
                continue
            if nc < dist.get(n, 999):
                dist[n] = nc
                q.append((n, nc))
    return 999


def _parse_hex_board(state, player, board_size):
    """Parse x/o from observation string."""
    obs = state.observation_string(player)
    my_char = 'x' if player == 0 else 'o'
    opp_char = 'o' if player == 0 else 'x'
    my_stones, opp_stones = set(), set()
    pos = 0
    for line in obs.split('\n'):
        for ch in line.lstrip():
            if ch in ('x', 'o', '.'):
                if ch == my_char: my_stones.add(pos)
                elif ch == opp_char: opp_stones.add(pos)
                pos += 1
    return my_stones, opp_stones


def _evaluate_hex(state, player, board_size, neighbors_fn):
    """Evaluate: opponent's path cost - our path cost. Higher = better for us."""
    if state.is_terminal():
        return state.returns()[player] * 10000

    my_stones, opp_stones = _parse_hex_board(state, player, board_size)
    empty = set(state.legal_actions(state.current_player())) if not state.is_terminal() else set()
    # Also add positions that are neither my nor opp (should be empty)
    all_occupied = my_stones | opp_stones
    empty = set(range(board_size * board_size)) - all_occupied

    my_cost = _shortest_path(board_size, empty, my_stones, player, neighbors_fn)
    opp_cost = _shortest_path(board_size, empty, opp_stones, 1 - player, neighbors_fn)

    return (opp_cost - my_cost) * 100 + len(my_stones)


def _minimax_hex(state, depth, alpha, beta, player, board_size, neighbors_fn):
    """Minimax with alpha-beta for hex."""
    if depth == 0 or state.is_terminal():
        return _evaluate_hex(state, player, board_size, neighbors_fn), None

    cp = state.current_player()
    if cp < 0:
        return _evaluate_hex(state, player, board_size, neighbors_fn), None

    legal = state.legal_actions(cp)
    if not legal:
        return _evaluate_hex(state, player, board_size, neighbors_fn), None

    maximizing = (cp == player)
    best_action = legal[0]

    if maximizing:
        max_eval = -999999
        for a in legal:
            child = state.child(a)
            val, _ = _minimax_hex(child, depth - 1, alpha, beta, player, board_size, neighbors_fn)
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
            val, _ = _minimax_hex(child, depth - 1, alpha, beta, player, board_size, neighbors_fn)
            if val < min_eval:
                min_eval = val
                best_action = a
            beta = min(beta, val)
            if beta <= alpha:
                break
        return min_eval, best_action


def hex_bot(state, player):
    legal = state.legal_actions(player)
    if not legal:
        return 0, "No legal moves."

    board_size = int(state.get_game().num_distinct_actions() ** 0.5)
    rc, neighbors_fn = _make_board_utils(board_size)
    center = board_size // 2

    # Determine search depth based on board fill
    filled = board_size * board_size - len(legal)
    if filled > board_size * board_size - 8:
        depth = 6  # endgame
    elif board_size <= 5:
        depth = 4
    else:
        depth = 3  # larger boards: shallower due to branching

    # First move: always center
    if filled == 0:
        a = center * board_size + center
        if a in legal:
            r, c = rc(a)
            return a, (f"Opening move: taking center ({r},{c}) on {board_size}x{board_size} board. "
                       f"The center maximizes connection paths in all directions and forces opponent to react.")

    val, best_action = _minimax_hex(state, depth, -999999, 999999, player, board_size, neighbors_fn)

    r, c = rc(best_action)
    my_stones, opp_stones = _parse_hex_board(state, player, board_size)
    empty = set(range(board_size * board_size)) - my_stones - opp_stones
    my_cost = _shortest_path(board_size, empty - {best_action}, my_stones | {best_action}, player, neighbors_fn)
    adj_my = sum(1 for n in neighbors_fn(best_action) if n in my_stones)
    target = "top-to-bottom" if player == 0 else "left-to-right"

    if val > 5000:
        think = (f"Minimax finds a winning path through ({r},{c}). "
                 f"Our {target} connection is now guaranteed within {my_cost} moves. "
                 f"Opponent cannot block all routes simultaneously.")
    elif adj_my >= 2:
        think = (f"Position ({r},{c}) connects {adj_my} existing stones, creating a strong bridge pattern. "
                 f"Minimax (depth {depth}) confirms this strengthens our {target} chain. "
                 f"Need {my_cost} more cells to complete the connection.")
    elif adj_my == 1:
        think = (f"Extending our chain to ({r},{c}), linking to an adjacent stone. "
                 f"Looking {depth} moves ahead, this path toward {target} edges is strongest. "
                 f"Connection cost: {my_cost} cells remaining.")
    else:
        think = (f"Playing ({r},{c}) on {board_size}x{board_size} board. "
                 f"Minimax evaluation (depth {depth}) favors this for {target} connection. "
                 f"Balancing our path ({my_cost} cells needed) with blocking opponent's progress.")

    return best_action, think
