"""Clobber bot v2: minimax with alpha-beta pruning.

v1: 3-step lookahead → ~6% vs MCTS 1500sim
v2: alpha-beta minimax (depth 5) + mobility evaluation
"""


def _evaluate(state, player):
    """Evaluate: our mobility - opponent mobility."""
    if state.is_terminal():
        returns = state.returns()
        return returns[player] * 10000

    # In clobber, only current player has legal actions
    # Must check both players' potential moves
    cp = state.current_player()
    if cp < 0:
        return 0

    # Count moves for both players by checking the state
    if cp == player:
        my_moves = len(state.legal_actions(player))
        # Estimate opp moves: play a random move, check opp's legal actions
        opp_moves = 0
        for a in state.legal_actions(player)[:3]:
            child = state.child(a)
            if not child.is_terminal() and child.current_player() >= 0:
                opp_moves = max(opp_moves, len(child.legal_actions(child.current_player())))
    else:
        opp_moves = len(state.legal_actions(cp))
        my_moves = 0
        for a in state.legal_actions(cp)[:3]:
            child = state.child(a)
            if not child.is_terminal() and child.current_player() >= 0:
                my_moves = max(my_moves, len(child.legal_actions(child.current_player())))

    return (my_moves - opp_moves) * 10 + my_moves


def _minimax(state, depth, alpha, beta, player):
    """Minimax with alpha-beta pruning for clobber."""
    if depth == 0 or state.is_terminal():
        return _evaluate(state, player), None

    cp = state.current_player()
    if cp < 0:
        return _evaluate(state, player), None

    legal = state.legal_actions(cp)
    if not legal:
        return _evaluate(state, player), None

    maximizing = (cp == player)
    best_action = legal[0]

    if maximizing:
        max_eval = -999999
        for a in legal:
            child = state.child(a)
            val, _ = _minimax(child, depth - 1, alpha, beta, player)
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
            val, _ = _minimax(child, depth - 1, alpha, beta, player)
            if val < min_eval:
                min_eval = val
                best_action = a
            beta = min(beta, val)
            if beta <= alpha:
                break
        return min_eval, best_action


def clobber_bot(state, player):
    legal = state.legal_actions(player)
    if not legal:
        return 0, "No legal moves."

    # Check for immediate wins
    for a in legal:
        child = state.child(a)
        if child.is_terminal():
            name = state.action_to_string(player, a)
            return a, f"Capturing at {name[2:4]} ends the game — opponent has no moves. Taking the winning move immediately."

    # Deeper search = better results, especially in endgame
    total_moves = len(legal)
    if total_moves <= 5:
        depth = 12  # endgame: solve exactly
    elif total_moves <= 10:
        depth = 8
    elif total_moves <= 20:
        depth = 6
    else:
        depth = 5

    val, best_action = _minimax(state, depth, -999999, 999999, player)
    name = state.action_to_string(player, best_action)
    capture_pos = name[2:4] if len(name) >= 4 else name

    child = state.child(best_action)
    if not child.is_terminal():
        cp = child.current_player()
        if cp == player:
            opp_moves = 0
            my_next = len(child.legal_actions(player))
        else:
            opp_moves = len(child.legal_actions(cp)) if cp >= 0 else 0
            # Estimate our moves after opponent's turn
            my_next = 0
            for oa in child.legal_actions(cp)[:3]:
                gc = child.child(oa)
                if not gc.is_terminal() and gc.current_player() == player:
                    my_next = max(my_next, len(gc.legal_actions(player)))
    else:
        opp_moves = 0
        my_next = 0

    if val > 5000:
        think = (f"Minimax (depth {depth}) finds a winning line starting with capture at {capture_pos}. "
                 f"Evaluation {val} indicates forced advantage — opponent cannot recover "
                 f"regardless of their response. Taking the winning path.")
    elif opp_moves <= 3:
        think = (f"Capturing at {capture_pos} leaves opponent with only {opp_moves} responses "
                 f"(depth-{depth} search, eval {val}). This strong positional squeeze "
                 f"limits opponent's options while we maintain {my_next} follow-up moves.")
    elif val > 0:
        think = (f"Minimax (depth {depth}) selects capture at {capture_pos} with positive evaluation ({val}). "
                 f"Opponent has {opp_moves} responses but our mobility advantage ({my_next} moves) "
                 f"is maintained through the search horizon.")
    else:
        think = (f"Difficult position — minimax (depth {depth}) at {capture_pos} evaluates to {val}. "
                 f"Opponent has {opp_moves} responses vs our {my_next}. "
                 f"This is the least bad option; deeper search may reveal better prospects.")

    return best_action, think
