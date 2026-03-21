"""Clobber bot v2: minimax with alpha-beta pruning.

v1: 3-step lookahead → ~6% vs MCTS 1500sim
v2: alpha-beta minimax (depth 5) + mobility evaluation
"""


def _parse_clobber_board(state, player):
    """Parse board to count pieces and isolated pieces."""
    obs = state.observation_string(player)
    my_char = 'x' if player == 0 else 'o'
    opp_char = 'o' if player == 0 else 'x'
    my_pieces, opp_pieces = 0, 0
    for ch in obs:
        if ch == my_char: my_pieces += 1
        elif ch == opp_char: opp_pieces += 1
    return my_pieces, opp_pieces


def _evaluate(state, player):
    """Evaluate: mobility + piece count + endgame detection."""
    if state.is_terminal():
        returns = state.returns()
        return returns[player] * 10000

    cp = state.current_player()
    if cp < 0:
        return 0

    # Current player's moves
    current_moves = len(state.legal_actions(cp))

    # Piece count advantage
    my_p, opp_p = _parse_clobber_board(state, player)
    piece_advantage = (my_p - opp_p) * 3

    # Mobility: who has more moves matters most
    if cp == player:
        return current_moves * 10 + piece_advantage
    else:
        return -current_moves * 10 + piece_advantage


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

    # Move ordering: try moves that reduce opponent mobility first (better pruning)
    def move_priority(a):
        child = state.child(a)
        if child.is_terminal():
            return -99999 if maximizing else 99999  # winning move first
        cp2 = child.current_player()
        return -len(child.legal_actions(cp2)) if cp2 >= 0 else 0

    sorted_legal = sorted(legal, key=move_priority)

    if maximizing:
        max_eval = -999999
        for a in sorted_legal:
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
        for a in sorted_legal:
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
    # Move ordering enables deeper search with better pruning
    if total_moves <= 5:
        depth = 10
    elif total_moves <= 10:
        depth = 8
    elif total_moves <= 20:
        depth = 7
    else:
        depth = 6

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
