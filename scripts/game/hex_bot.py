"""Hex bot: connectivity-aware + center control + dynamic board size."""


def hex_bot(state, player):
    legal = state.legal_actions(player)
    if not legal:
        return 0, "No legal moves."

    board_size = int(state.get_game().num_distinct_actions() ** 0.5)
    center = board_size // 2
    occupied = set(range(board_size * board_size)) - set(legal)

    def neighbors(pos):
        r, c = pos // board_size, pos % board_size
        nbrs = []
        for dr, dc in [(-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < board_size and 0 <= nc < board_size:
                nbrs.append(nr * board_size + nc)
        return nbrs

    def score_pos(a):
        r, c = a // board_size, a % board_size
        center_dist = abs(r - center) + abs(c - center)
        adj_occupied = sum(1 for n in neighbors(a) if n in occupied)
        if player == 0:
            edge_progress = min(r, board_size - 1 - r)
        else:
            edge_progress = min(c, board_size - 1 - c)
        return center_dist * 2 - adj_occupied * 5 + edge_progress

    best = min(legal, key=score_pos)
    r, c = best // board_size, best % board_size
    adj_count = sum(1 for n in neighbors(best) if n in occupied)
    center_dist = abs(r - center) + abs(c - center)
    target = "top-to-bottom" if player == 0 else "left-to-right"

    if center_dist == 0:
        think = f"Taking center ({r},{c}) on a {board_size}x{board_size} board — the strongest opening position in Hex. It maximizes connection paths toward both {target} edges and forces opponent to play reactively."
    elif adj_count >= 2:
        think = f"Position ({r},{c}) connects to {adj_count} existing stones, creating a bridge pattern that strengthens our {target} chain. Multiple adjacencies make this position hard for opponent to cut."
    elif adj_count == 1:
        think = f"Position ({r},{c}) extends our chain by linking to an adjacent stone. Building incrementally toward a {target} connection while maintaining flexibility for future moves."
    elif center_dist <= 2:
        think = f"Near-center position ({r},{c}) on {board_size}x{board_size} board. Central positions have the most connection options and put pressure on opponent to respond rather than build their own path."
    else:
        think = f"Position ({r},{c}) advances toward the {target.split('-')[1]} edge. With center already contested, expanding toward the target edge is necessary to complete the winning connection."

    return best, think
