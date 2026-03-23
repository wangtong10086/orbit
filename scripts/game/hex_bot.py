"""Hex bot v8: Strategy-based + MCTS — bridge patterns, ladder, edge templates.

Hex has a proven first-player winning strategy (Nash 1952).
Key patterns that SFT CAN learn (unlike raw MCTS):
1. Bridge: two stones sharing 2 empty neighbors = unbreakable virtual connection
2. Ladder: force opponent to block one path while building another
3. Edge template: known winning shapes near board edges
4. Center control: first move center, expand outward

MCTS selects the move. Strategy engine generates PATTERN-BASED think chains
that reference specific learnable concepts (bridge/ladder/template).
"""

from collections import deque
from mcts_helper import get_mcts_bot


def _neighbors(pos, bs):
    r, c = pos // bs, pos % bs
    nbrs = []
    for dr, dc in [(-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0)]:
        nr, nc = r + dr, c + dc
        if 0 <= nr < bs and 0 <= nc < bs:
            nbrs.append(nr * bs + nc)
    return nbrs


def _parse_board(state, player, bs):
    obs = state.observation_string(player)
    my_char = 'x' if player == 0 else 'o'
    opp_char = 'o' if player == 0 else 'x'
    my_stones, opp_stones = set(), set()
    pos = 0
    for line in obs.split('\n'):
        for ch in line.lstrip():
            if ch in ('x', 'o', '.'):
                if ch == my_char:
                    my_stones.add(pos)
                elif ch == opp_char:
                    opp_stones.add(pos)
                pos += 1
    return my_stones, opp_stones


def _shortest_path(bs, empty_set, stones, player):
    if player == 0:
        sources = [p for p in range(bs) if p in stones or p in empty_set]
        targets = set(range(bs * (bs - 1), bs * bs))
    else:
        sources = [p for p in range(0, bs * bs, bs) if p in stones or p in empty_set]
        targets = set(range(bs - 1, bs * bs, bs))
    dist = {}
    q = deque()
    for s in sources:
        cost = 0 if s in stones else 1
        if cost < dist.get(s, 999):
            dist[s] = cost
            q.append((s, cost))
    while q:
        pos, cost = q.popleft()
        if cost > dist.get(pos, 999):
            continue
        if pos in targets:
            return cost
        for n in _neighbors(pos, bs):
            if n in stones:
                nc = cost
            elif n in empty_set:
                nc = cost + 1
            else:
                continue
            if nc < dist.get(n, 999):
                dist[n] = nc
                q.append((n, nc))
    return 999


def _find_bridges(stones, bs):
    """Find bridge patterns: pairs of own stones connected by virtual connection.
    A bridge exists when two stones share exactly 2 common empty neighbors."""
    bridges = []
    for s in stones:
        s_nbrs = set(_neighbors(s, bs))
        for t in stones:
            if t <= s:
                continue
            t_nbrs = set(_neighbors(t, bs))
            # Common neighbors that are empty
            common = s_nbrs & t_nbrs - stones
            if len(common) == 2:
                bridges.append((s, t, common))
    return bridges


def _find_ladder_threat(my_stones, opp_stones, bs, player):
    """Detect if opponent is building a ladder (forcing us along an edge)."""
    # Check if opponent has 3+ stones in a line toward their goal
    if player == 0:  # we go top-bottom, opponent goes left-right
        opp_cols = [s % bs for s in opp_stones]
        if len(opp_cols) >= 3:
            min_c, max_c = min(opp_cols), max(opp_cols)
            if max_c - min_c >= bs // 2:
                return True, "left-to-right"
    else:
        opp_rows = [s // bs for s in opp_stones]
        if len(opp_rows) >= 3:
            min_r, max_r = min(opp_rows), max(opp_rows)
            if max_r - min_r >= bs // 2:
                return True, "top-to-bottom"
    return False, ""


def _edge_distance(pos, bs, player):
    """Distance to each target edge."""
    r, c = pos // bs, pos % bs
    if player == 0:  # top-bottom
        return r, bs - 1 - r  # dist to top, dist to bottom
    else:  # left-right
        return c, bs - 1 - c  # dist to left, dist to right


def _explain_hex_move(state, player, action, bs):
    """Generate strategy-based think referencing learnable patterns."""
    my_stones, opp_stones = _parse_board(state, player, bs)
    all_occ = my_stones | opp_stones
    empty = set(range(bs * bs)) - all_occ
    r, c = action // bs, action % bs
    target = "top-to-bottom" if player == 0 else "left-to-right"
    opp_target = "left-to-right" if player == 0 else "top-to-bottom"
    turn = (len(all_occ) // 2) + 1

    new_my = my_stones | {action}
    new_empty = empty - {action}
    old_my_cost = _shortest_path(bs, empty, my_stones, player)
    my_cost = _shortest_path(bs, new_empty, new_my, player)
    opp_cost = _shortest_path(bs, new_empty, opp_stones, 1 - player)
    old_opp_cost = _shortest_path(bs, empty, opp_stones, 1 - player)

    # Analyze neighbors
    adj_my = [n for n in _neighbors(action, bs) if n in my_stones]
    adj_opp = [n for n in _neighbors(action, bs) if n in opp_stones]

    # Find bridges involving the new stone
    new_bridges = _find_bridges(new_my, bs)
    bridges_with_action = [(s, t, common) for s, t, common in new_bridges if action in (s, t)]

    # Ladder detection
    ladder_threat, ladder_dir = _find_ladder_threat(my_stones, opp_stones, bs, player)

    # Edge distances
    d_near, d_far = _edge_distance(action, bs, player)

    # Connection to edges
    def touches_edge(stones, p):
        if p == 0:
            top = any(s < bs for s in stones)
            bot = any(s >= bs * (bs - 1) for s in stones)
            return top, bot, "top", "bottom"
        else:
            left = any(s % bs == 0 for s in stones)
            right = any(s % bs == bs - 1 for s in stones)
            return left, right, "left", "right"

    e1, e2, e1_name, e2_name = touches_edge(new_my, player)
    oe1, oe2, _, _ = touches_edge(opp_stones, 1 - player)

    parts = []

    # 1. Opening
    if len(all_occ) == 0:
        center = bs // 2
        if r == center and c == center:
            parts.append(f"Opening: center ({r},{c}) on {bs}x{bs}. "
                        f"In hex, the first player has a proven winning strategy. "
                        f"Center maximizes connections to all edges and controls the board.")
        else:
            parts.append(f"Opening: ({r},{c}) on {bs}x{bs}. "
                        f"Near-center placement to control key connection paths.")
        return " ".join(parts)

    # 2. Winning move
    if my_cost == 0:
        parts.append(f"({r},{c}) completes our {target} connection — winning! "
                    f"Our chain now reaches both edges.")
        if bridges_with_action:
            parts.append(f"This was secured by bridge patterns that opponent couldn't block.")
        return " ".join(parts)

    # 3. Bridge creation (KEY LEARNABLE PATTERN)
    if bridges_with_action:
        s, t, common = bridges_with_action[0]
        other = s if t == action else t
        or_r, or_c = other // bs, other % bs
        parts.append(f"Bridge pattern: ({r},{c}) creates a virtual connection with our stone at "
                    f"({or_r},{or_c}). They share two empty neighbors — "
                    f"opponent cannot block both, so this connection is guaranteed. "
                    f"Bridges are the key to winning hex: unbreakable links toward {target} edge.")
    elif len(adj_my) >= 2:
        coords = [f"({n//bs},{n%bs})" for n in adj_my[:3]]
        parts.append(f"({r},{c}) connects {len(adj_my)} of our stones ({', '.join(coords)}), "
                    f"strengthening our chain. Looking for bridge opportunities in next moves.")

    # 4. Blocking opponent
    if not parts and old_opp_cost < opp_cost:
        blocked = old_opp_cost - opp_cost if opp_cost < 999 else old_opp_cost
        parts.append(f"Defensive: ({r},{c}) blocks opponent's {opp_target} path. "
                    f"Their connection cost increased from {old_opp_cost} to {opp_cost}. ")
        if oe1 and oe2:
            parts.append(f"Critical — opponent was close to connecting both edges!")
        if ladder_threat:
            parts.append(f"Opponent was building a ladder ({ladder_dir}), this disrupts it.")

    # 5. Extending toward edge
    if not parts and len(adj_my) == 1:
        parent = adj_my[0]
        pr, pc = parent // bs, parent % bs
        if my_cost < old_my_cost:
            parts.append(f"Extending chain from ({pr},{pc}) toward {e2_name} edge via ({r},{c}). "
                        f"Path cost reduced from {old_my_cost} to {my_cost}. "
                        f"Each step closer to the edge makes our connection harder to block.")
        else:
            parts.append(f"Extending from ({pr},{pc}) to ({r},{c}), maintaining our {target} path. "
                        f"Need {my_cost} more cells to complete connection.")

    # 6. Ladder response
    if not parts and ladder_threat:
        parts.append(f"Responding to opponent's ladder ({ladder_dir}): ({r},{c}) "
                    f"breaks the forced sequence. In hex, the key to beating ladders is "
                    f"placing stones that serve dual purpose — blocking AND advancing our own path.")

    # 7. Strategic placement (no direct connection)
    if not parts:
        if d_near <= 1:
            parts.append(f"({r},{c}) near {e1_name} edge (distance {d_near}). "
                        f"Anchoring our chain to the edge — once connected to an edge, "
                        f"we only need to reach the other side ({d_far} cells away).")
        elif adj_opp:
            opp_coords = [f"({n//bs},{n%bs})" for n in adj_opp[:2]]
            parts.append(f"({r},{c}) placed adjacent to opponent's stones at {', '.join(opp_coords)}. "
                        f"Contesting this area prevents opponent from building unblocked connections here.")
        else:
            parts.append(f"({r},{c}) strategic placement in turn {turn}. "
                        f"Building a second path option — in hex, having multiple potential "
                        f"connections forces opponent to defend everywhere.")

    # 8. Status summary
    status = f"Path race: we need {my_cost}, opponent needs {opp_cost}. "
    if e1:
        status += f"Connected to {e1_name}. "
    if e2:
        status += f"Connected to {e2_name}. "
    if e1 and e2:
        status += "Both edges reached — completing connection! "
    parts.append(f"Stones: {len(new_my)} ours, {len(opp_stones)} opponent, {bs}x{bs} board. {status}")

    return " ".join(parts)


def hex_bot(state, player):
    legal = state.legal_actions(player)
    if not legal:
        return 0, "No legal moves."

    bs = int(state.get_game().num_distinct_actions() ** 0.5)
    game = state.get_game()
    bot = get_mcts_bot(game, "hex")

    if bot is not None:
        try:
            action = bot.step(state)
            if action in legal:
                think = _explain_hex_move(state, player, action, bs)
                return action, think
        except Exception:
            pass

    # Fallback: center
    center = bs // 2
    a = center * bs + center
    if a in legal:
        return a, "Taking center position."
    return legal[0], "Taking available move."
