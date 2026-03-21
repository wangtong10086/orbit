"""Othello bot: positional weights + mobility minimization."""


def othello_bot(state, player):
    legal = state.legal_actions(player)
    if not legal:
        return 0, "No legal moves available, must pass."

    # Classic othello positional weight table
    w = [
        [100, -20, 10,  5,  5, 10, -20, 100],
        [-20, -50, -2, -2, -2, -2, -50, -20],
        [ 10,  -2,  5,  1,  1,  5,  -2,  10],
        [  5,  -2,  1,  0,  0,  1,  -2,   5],
        [  5,  -2,  1,  0,  0,  1,  -2,   5],
        [ 10,  -2,  5,  1,  1,  5,  -2,  10],
        [-20, -50, -2, -2, -2, -2, -50, -20],
        [100, -20, 10,  5,  5, 10, -20, 100],
    ]
    weights = {r * 8 + c: w[r][c] for r in range(8) for c in range(8)}
    corners = {0, 7, 56, 63}

    best_action = legal[0]
    best_score = -9999

    for a in legal:
        pos_w = weights.get(a, 0)
        child = state.child(a)
        if child.is_terminal():
            r, c = a // 8, a % 8
            return a, f"Playing ({r},{c}) ends the game. Taking it to finalize the disc count in our favor."

        opp = child.current_player()
        opp_mob = len(child.legal_actions(opp)) if opp >= 0 else 0
        total = pos_w * 3 - opp_mob * 2

        if total > best_score:
            best_score = total
            best_action = a

    r, c = best_action // 8, best_action % 8
    pos_w = weights.get(best_action, 0)
    child = state.child(best_action)
    opp = child.current_player()
    opp_mob = len(child.legal_actions(opp)) if opp >= 0 else 0

    if best_action in corners:
        think = f"Corner ({r},{c}) is available — corners cannot be flipped and anchor stable disc chains. This is always the top priority move in Othello regardless of other considerations."
    elif pos_w >= 10:
        think = f"Position ({r},{c}) has high positional value ({pos_w}) as an edge square. It restricts opponent to {opp_mob} responses and provides stable territory that's difficult to overturn."
    elif pos_w < -10:
        think = f"Position ({r},{c}) is a risky square (weight {pos_w}, near a corner), but it's the best available option. It leaves opponent with {opp_mob} moves, which is the minimum achievable from current legal options."
    else:
        think = f"Position ({r},{c}) scores {pos_w} positionally and limits opponent to {opp_mob} moves. Balancing board control with mobility restriction — no corner or strong edge available this turn."

    return best_action, think
