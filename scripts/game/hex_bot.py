"""Hex bot v2: shortest path + virtual connections + opponent blocking.

v1: center control + distance → 0% vs MCTS
v2: BFS shortest path to edges + block opponent's path + virtual connections
"""

from collections import deque


def hex_bot(state, player):
    legal = state.legal_actions(player)
    if not legal:
        return 0, "No legal moves."

    board_size = int(state.get_game().num_distinct_actions() ** 0.5)
    center = board_size // 2

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

    # Parse board from observation: 'x' = player 0, 'o' = player 1
    obs = state.observation_string(player)
    my_stones = set()
    opp_stones = set()
    my_char = 'x' if player == 0 else 'o'
    opp_char = 'o' if player == 0 else 'x'
    pos = 0
    for line in obs.split('\n'):
        stripped = line.lstrip()
        for ch in stripped:
            if ch in ('x', 'o', '.'):
                if ch == my_char:
                    my_stones.add(pos)
                elif ch == opp_char:
                    opp_stones.add(pos)
                pos += 1

    def shortest_path_cost(empty_set, my_stones, p):
        """BFS-based: minimum empty cells needed to connect player p's two edges.
        Player 0: top-bottom. Player 1: left-right."""
        # Sources: player's edge cells
        if p == 0:
            sources = [pos for pos in range(board_size) if pos in my_stones or pos in empty_set]  # top row
            targets = set(range(board_size * (board_size - 1), board_size * board_size))  # bottom row
        else:
            sources = [pos for pos in range(0, board_size * board_size, board_size) if pos in my_stones or pos in empty_set]
            targets = set(range(board_size - 1, board_size * board_size, board_size))

        # BFS with cost = number of empty cells used
        dist = {}
        q = deque()
        for s in sources:
            cost = 0 if s in my_stones else 1
            if s not in dist or cost < dist[s]:
                dist[s] = cost
                q.append((s, cost))

        while q:
            pos, cost = q.popleft()
            if cost > dist.get(pos, 999):
                continue
            if pos in targets:
                return cost
            for n in neighbors(pos):
                if n in my_stones:
                    nc = cost
                elif n in empty_set:
                    nc = cost + 1
                else:
                    continue  # opponent's stone, can't use
                if nc < dist.get(n, 999):
                    dist[n] = nc
                    q.append((n, nc))
        return 999

    empty = set(legal)

    # Evaluate each legal move
    best_action = legal[0]
    best_score = -9999
    best_info = {}

    for a in legal:
        r, c = rc(a)

        # Simulate placing here
        new_my = my_stones | {a}
        new_empty = empty - {a}

        # Our path cost improvement
        my_cost_before = shortest_path_cost(empty, my_stones, player)
        my_cost_after = shortest_path_cost(new_empty, new_my, player)
        my_improvement = my_cost_before - my_cost_after

        # Blocking: placing here removes this cell from opponent's paths
        opp = 1 - player
        # For opponent's path: their stones are free, our stones block, empty cells cost 1
        # Before: opponent can use this cell (it's empty)
        opp_cost_before = shortest_path_cost(empty, opp_stones, opp)
        # After: we placed here, opponent can't use it (it's ours now)
        opp_cost_after = shortest_path_cost(new_empty, opp_stones, opp)
        opp_disruption = opp_cost_after - opp_cost_before

        # Center bonus
        center_dist = abs(r - center) + abs(c - center)
        center_bonus = max(0, (board_size - center_dist)) * 0.5

        # Adjacency bonus
        adj_my = sum(1 for n in neighbors(a) if n in my_stones)

        # Combined score: shorten our path + block opponent + positional
        # Key: both offense and defense matter equally
        score = my_improvement * 20 + opp_disruption * 20 + center_bonus + adj_my * 4

        # Bonus: if this move connects two of our groups
        if adj_my >= 2:
            score += 10  # bridge formation

        if score > best_score:
            best_score = score
            best_action = a
            best_info = {
                'my_improve': my_improvement,
                'opp_disrupt': opp_disruption,
                'adj': adj_my,
                'my_cost': my_cost_after,
            }

    r, c = rc(best_action)
    bi = best_info
    target = "top-to-bottom" if player == 0 else "left-to-right"

    if bi.get('my_improve', 0) > 0 and bi.get('opp_disrupt', 0) > 0:
        think = (f"Position ({r},{c}) serves dual purpose: shortens our {target} path by {bi['my_improve']} steps "
                 f"while extending opponent's path by {bi['opp_disrupt']} steps. "
                 f"Our connection now needs {bi['my_cost']} more cells. "
                 f"This two-way value makes it the strongest available move.")
    elif bi.get('my_improve', 0) > 0:
        think = (f"Position ({r},{c}) reduces our {target} connection cost by {bi['my_improve']} steps "
                 f"(now {bi['my_cost']} cells needed). "
                 f"{'Connects to ' + str(bi['adj']) + ' existing stones, strengthening the chain.' if bi.get('adj', 0) > 0 else 'Advances toward target edges.'}")
    elif bi.get('opp_disrupt', 0) > 0:
        think = (f"Position ({r},{c}) blocks opponent's path, adding {bi['opp_disrupt']} steps to their connection cost. "
                 f"Defensive move to prevent opponent from completing their chain while maintaining our options.")
    else:
        think = (f"Position ({r},{c}) on {board_size}x{board_size} board. "
                 f"Central positioning maintains flexibility for both connection building and opponent blocking. "
                 f"Path cost to complete: {bi.get('my_cost', '?')} cells.")

    return best_action, think
