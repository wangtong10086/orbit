"""Hex bot v7: MCTS search (5000 sim, 100 rollout) + BFS path explanation.

v1-v5: minimax + BFS path → 30% vs MCTS 1000sim/50roll
v6: MCTS 3000sim/10roll → 0% (rollouts too few, noisy signal)
v7: MCTS 5000sim/100roll (5x sim, 2x rollouts vs opponent) — proper signal
"""

from collections import deque
from mcts_helper import get_mcts_bot


def _parse_hex_board(state, player, board_size):
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


def _neighbors(pos, board_size):
    r, c = pos // board_size, pos % board_size
    nbrs = []
    for dr, dc in [(-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0)]:
        nr, nc = r + dr, c + dc
        if 0 <= nr < board_size and 0 <= nc < board_size:
            nbrs.append(nr * board_size + nc)
    return nbrs


def _shortest_path(board_size, empty_set, player_stones, player):
    if player == 0:  # top-bottom
        sources = [p for p in range(board_size) if p in player_stones or p in empty_set]
        targets = set(range(board_size * (board_size - 1), board_size * board_size))
    else:  # left-right
        sources = [p for p in range(0, board_size * board_size, board_size)
                   if p in player_stones or p in empty_set]
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
        if cost > dist.get(pos, 999): continue
        if pos in targets: return cost
        for n in _neighbors(pos, board_size):
            if n in player_stones: nc = cost
            elif n in empty_set: nc = cost + 1
            else: continue
            if nc < dist.get(n, 999):
                dist[n] = nc
                q.append((n, nc))
    return 999


def _explain_hex_move(state, player, action, board_size):
    """Generate state-specific hex think referencing board topology."""
    my_stones, opp_stones = _parse_hex_board(state, player, board_size)
    all_occupied = my_stones | opp_stones
    empty = set(range(board_size * board_size)) - all_occupied
    r, c = action // board_size, action % board_size
    target = "top-to-bottom" if player == 0 else "left-to-right"
    opp_target = "left-to-right" if player == 0 else "top-to-bottom"

    # Path costs before and after
    old_my_cost = _shortest_path(board_size, empty, my_stones, player)
    old_opp_cost = _shortest_path(board_size, empty, opp_stones, 1 - player)
    new_my = my_stones | {action}
    new_empty = empty - {action}
    my_cost = _shortest_path(board_size, new_empty, new_my, player)
    opp_cost = _shortest_path(board_size, new_empty, opp_stones, 1 - player)

    # Neighbors analysis
    adj_my = [n for n in _neighbors(action, board_size) if n in my_stones]
    adj_opp = [n for n in _neighbors(action, board_size) if n in opp_stones]
    adj_my_pos = [(n // board_size, n % board_size) for n in adj_my]
    adj_opp_pos = [(n // board_size, n % board_size) for n in adj_opp]

    filled = len(all_occupied)
    turn = filled // 2 + 1
    total_cells = board_size * board_size

    # Which edges do our stones touch?
    def edge_contact(stones, p):
        if p == 0:  # top-bottom
            top = any(s < board_size for s in stones)
            bot = any(s >= board_size * (board_size - 1) for s in stones)
            return top, bot, "top edge", "bottom edge"
        else:
            left = any(s % board_size == 0 for s in stones)
            right = any(s % board_size == board_size - 1 for s in stones)
            return left, right, "left edge", "right edge"

    my_e1, my_e2, e1_name, e2_name = edge_contact(new_my, player)
    opp_e1, opp_e2, oe1_name, oe2_name = edge_contact(opp_stones, 1 - player)

    # Region of the board
    if r < board_size // 3:
        region = "upper" if player == 0 else "left"
    elif r > board_size * 2 // 3:
        region = "lower" if player == 0 else "right"
    else:
        region = "central"

    parts = []

    # 1. Context: turn, board size, position
    parts.append(f"Turn {turn} on {board_size}x{board_size} board. Playing ({r},{c}) in the {region} zone.")

    # 2. Immediate tactical impact
    if my_cost == 0:
        parts.append(f"This completes our {target} connection — winning move!")
    elif len(adj_my) >= 2:
        coords = [f"({pr},{pc})" for pr, pc in adj_my_pos[:3]]
        parts.append(f"Bridges {len(adj_my)} of our stones ({', '.join(coords)}), "
                     f"creating a strong connected group.")
    elif len(adj_my) == 1:
        pr, pc = adj_my_pos[0]
        parts.append(f"Extends from our stone at ({pr},{pc}).")
    elif len(adj_opp) > 0:
        coords = [f"({pr},{pc})" for pr, pc in adj_opp_pos[:2]]
        parts.append(f"Placed adjacent to opponent's stone(s) at {', '.join(coords)} — "
                     f"contesting this area.")
    else:
        parts.append(f"An isolated placement preparing a future connection point.")

    # 3. Path analysis — how this changes the race
    if old_my_cost != my_cost or old_opp_cost != opp_cost:
        my_change = old_my_cost - my_cost
        opp_change = opp_cost - old_opp_cost
        if my_change > 0:
            parts.append(f"Our {target} path shortened by {my_change} "
                         f"(from {old_my_cost} to {my_cost} cells needed).")
        if opp_change > 0:
            parts.append(f"Opponent's {opp_target} path lengthened by {opp_change} "
                         f"(from {old_opp_cost} to {opp_cost}).")
    parts.append(f"Path race: we need {my_cost} more cells, opponent needs {opp_cost}.")

    # 4. Edge connectivity status
    edge_parts = []
    if my_e1 and my_e2:
        edge_parts.append(f"Our chain touches both {e1_name} and {e2_name} — near completion!")
    elif my_e1:
        edge_parts.append(f"Connected to {e1_name}, building toward {e2_name}.")
    elif my_e2:
        edge_parts.append(f"Connected to {e2_name}, building toward {e1_name}.")
    if opp_e1 and opp_e2:
        edge_parts.append(f"Warning: opponent touches both their edges!")
    if edge_parts:
        parts.append(" ".join(edge_parts))

    # 5. Strategic note
    if opp_cost <= 2 and my_cost > 2:
        parts.append(f"Urgent defense — opponent is {opp_cost} cells from winning.")
    elif my_cost <= 2 and opp_cost > 2:
        parts.append(f"Close to winning — just {my_cost} cell(s) from completing our path.")
    elif my_cost < opp_cost:
        parts.append(f"Leading the path race by {opp_cost - my_cost} cell(s).")
    elif opp_cost < my_cost:
        parts.append(f"Behind in path race by {my_cost - opp_cost} cell(s) — need to catch up.")

    parts.append(f"Stones: {len(new_my)} ours, {len(opp_stones)} opponent, "
                 f"{total_cells - filled - 1} empty.")

    return " ".join(parts)


def hex_bot(state, player):
    legal = state.legal_actions(player)
    if not legal:
        return 0, "No legal moves."

    board_size = int(state.get_game().num_distinct_actions() ** 0.5)
    game = state.get_game()
    bot = get_mcts_bot(game, "hex")

    if bot is not None:
        try:
            action = bot.step(state)
            if action in legal:
                think = _explain_hex_move(state, player, action, board_size)
                return action, think
        except Exception:
            pass

    # Fallback: center
    center = board_size // 2
    a = center * board_size + center
    if a in legal:
        return a, f"Taking center position as fallback."
    return legal[0], "Taking available move."
