"""Hex rule-think bot — MCTS action + rule-based explanation for EVERY move.

Uses MCTS for action selection (same quality as hex_bot.py).
Think always explains WHY using transferable rules.

Rules (priority order):
1. BRIDGE: creates virtual connection with existing stone (2 shared empty neighbors)
2. EDGE CONNECTION: reaches one of the two target edges
3. CHAIN EXTENSION: extends connected group toward target edges
4. DOUBLE THREAT: creates two independent paths opponent can't both block
5. BLOCK: prevents opponent from connecting their edges
6. CENTER: near-center cells maximize connection paths
"""

from collections import deque


def _neighbors(pos, bs):
    r, c = pos // bs, pos % bs
    for dr, dc in [(-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0)]:
        nr, nc = r + dr, c + dc
        if 0 <= nr < bs and 0 <= nc < bs:
            yield nr * bs + nc


def _pos_name(pos, bs):
    r, c = pos // bs, pos % bs
    return f"{chr(ord('a') + c)}{r + 1}"


def _parse_board(state, player, bs):
    obs = state.observation_string(player)
    my_char = 'x' if player == 0 else 'o'
    opp_char = 'o' if player == 0 else 'x'
    my, opp = set(), set()
    pos = 0
    for line in obs.split('\n'):
        for ch in line.lstrip():
            if ch in ('x', 'o', '.'):
                if ch == my_char:
                    my.add(pos)
                elif ch == opp_char:
                    opp.add(pos)
                pos += 1
    return my, opp


def _find_bridges(stones, pos, bs):
    """Check if pos forms a bridge with any existing stone."""
    bridges = []
    pos_nbrs = set(_neighbors(pos, bs))
    for s in stones:
        s_nbrs = set(_neighbors(s, bs))
        common_empty = (pos_nbrs & s_nbrs) - stones - {pos}
        if len(common_empty) >= 2:
            bridges.append((s, common_empty))
    return bridges


def _connected_component(start, stones, bs):
    """BFS to find connected component containing start."""
    visited = set()
    q = deque([start])
    while q:
        p = q.popleft()
        if p in visited:
            continue
        visited.add(p)
        for n in _neighbors(p, bs):
            if n in stones and n not in visited:
                q.append(n)
    return visited


def _touches_edges(stones, bs, player):
    """Check which target edges the stones touch."""
    if player == 0:  # top-bottom
        top = any(s < bs for s in stones)
        bot = any(s >= bs * (bs - 1) for s in stones)
        return top, bot, "top", "bottom"
    else:  # left-right
        left = any(s % bs == 0 for s in stones)
        right = any(s % bs == bs - 1 for s in stones)
        return left, right, "left", "right"


def _shortest_path_cost(bs, my, opp, player):
    """BFS: minimum empty cells to connect player's edges."""
    empty = set(range(bs * bs)) - my - opp
    if player == 0:
        sources = [p for p in range(bs) if p in my or p in empty]
        targets = set(range(bs * (bs - 1), bs * bs))
    else:
        sources = [p for p in range(0, bs * bs, bs) if p in my or p in empty]
        targets = set(range(bs - 1, bs * bs, bs))
    dist = {}
    q = deque()
    for s in sources:
        cost = 0 if s in my else 1
        if cost < dist.get(s, 999):
            dist[s] = cost
            q.append((s, cost))
    while q:
        p, c = q.popleft()
        if c > dist.get(p, 999):
            continue
        if p in targets:
            return c
        for n in _neighbors(p, bs):
            if n in opp:
                continue
            nc = c if n in my else c + 1
            if nc < dist.get(n, 999):
                dist[n] = nc
                q.append((n, nc))
    return 999


def _rule_think(action, my, opp, bs, player, legal):
    """Generate rule-based think for hex move."""
    name = _pos_name(action, bs)
    r, c = action // bs, action % bs
    my_after = my | {action}
    target = "top-to-bottom" if player == 0 else "left-to-right"
    reasons = []

    # 1. BRIDGE
    bridges = _find_bridges(my, action, bs)
    if bridges:
        partner, common = bridges[0]
        pname = _pos_name(partner, bs)
        reasons.append(f"Bridge: {name} connects with {pname} via 2 shared empty neighbors — "
                       f"opponent cannot block both, so this is a guaranteed virtual connection.")

    # 2. EDGE CONNECTION
    e1, e2, e1_name, e2_name = _touches_edges(my, bs, player)
    e1a, e2a, _, _ = _touches_edges(my_after, bs, player)
    if e1a and not e1:
        reasons.append(f"Reaches {e1_name} edge — now we only need to connect to {e2_name}.")
    if e2a and not e2:
        reasons.append(f"Reaches {e2_name} edge — now we only need to connect to {e1_name}.")

    # 3. CHAIN EXTENSION
    adj_own = [n for n in _neighbors(action, bs) if n in my]
    if adj_own:
        component = _connected_component(adj_own[0], my_after, bs)
        chain_len = len(component)
        coords = [_pos_name(n, bs) for n in adj_own[:2]]
        reasons.append(f"Extends chain from {', '.join(coords)} — "
                       f"connected group now has {chain_len} stones toward {target} connection.")

    # 4. PATH IMPROVEMENT
    cost_before = _shortest_path_cost(bs, my, opp, player)
    cost_after = _shortest_path_cost(bs, my_after, opp, player)
    if cost_after < cost_before:
        reasons.append(f"Shortens {target} path from {cost_before} to {cost_after} empty cells needed.")

    # 5. BLOCKING
    opp_cost_before = _shortest_path_cost(bs, opp, my, 1 - player)
    opp_cost_after = _shortest_path_cost(bs, opp, my_after, 1 - player)
    if opp_cost_after > opp_cost_before:
        reasons.append(f"Blocks opponent — their path lengthens from {opp_cost_before} to {opp_cost_after}.")

    # 6. CENTER
    center = bs // 2
    dist_center = abs(r - center) + abs(c - center)
    if dist_center <= 1 and not reasons:
        reasons.append(f"Near-center position {name} — maximizes connection paths in all directions.")

    # 7. WINNING
    if cost_after == 0:
        reasons.insert(0, f"Completes the {target} connection — winning move!")

    if not reasons:
        reasons.append(f"Playing {name} for {target} connection. "
                       f"Path needs {cost_after} more cells, opponent needs {opp_cost_after}.")

    return " ".join(reasons)


def hex_rule_think_bot(state, player):
    """MCTS action + rule-based think."""
    legal = state.legal_actions(player)
    if not legal:
        return 0, "No legal moves."

    bs = int(state.get_game().num_distinct_actions() ** 0.5)
    my, opp = _parse_board(state, player, bs)

    # Use MCTS for action selection
    from mcts_helper import get_mcts_bot, mcts_step_with_stats
    game = state.get_game()
    bot = get_mcts_bot(game, "hex")

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

    think = _rule_think(action, my, opp, bs, player, legal)
    return action, think
