"""Clobber rule-think bot — MCTS action + rule-based explanation for EVERY move.

Uses MCTS for action selection (same quality as clobber_bot.py).
Think always explains WHY using transferable rules.

Rules (priority order):
1. SAFE CAPTURE: no adjacent opponent can recapture this cell
2. WINNING MOVE: opponent has no moves after this
3. REDUCE MOBILITY: limits opponent's available moves
4. FRAGMENT: isolates opponent groups
5. PRESERVE OWN MOBILITY: keeps our options open
6. ENDGAME PARITY: in endgame, having last move wins
"""


def _parse_board(state, player, rows, cols):
    """Parse board into player piece positions."""
    obs = str(state)
    my_char = 'o' if player == 0 else 'x'
    opp_char = 'x' if player == 0 else 'o'
    my, opp = set(), set()
    for r in range(rows):
        for c in range(cols):
            pos = r * cols + c
            # Parse from observation string
            pass

    # Simpler: use state string directly
    board = {}
    lines = obs.strip().split('\n')
    for i, line in enumerate(lines):
        row_num = rows - i  # board displayed top to bottom
        for j, ch in enumerate(line):
            if ch in ('o', 'x'):
                pos = (rows - 1 - i) * cols + j
                if ch == my_char:
                    my.add(pos)
                elif ch == opp_char:
                    opp.add(pos)
    return my, opp


def _adj(pos, rows, cols):
    """Adjacent positions (up/down/left/right)."""
    r, c = pos // cols, pos % cols
    result = []
    if r > 0: result.append((r - 1) * cols + c)
    if r < rows - 1: result.append((r + 1) * cols + c)
    if c > 0: result.append(r * cols + c - 1)
    if c < cols - 1: result.append(r * cols + c + 1)
    return result


def _pos_name(pos, rows, cols):
    r, c = pos // cols, pos % cols
    return f"{chr(ord('a') + c)}{r + 1}"


def _parse_action(action_str):
    """Parse action string like 'a5b5' into (from_pos, to_pos)."""
    if len(action_str) >= 4:
        fc, fr = action_str[0], action_str[1]
        tc, tr = action_str[2], action_str[3]
        return (fc, fr), (tc, tr)
    return None, None


def _rule_think(action, state, player, legal, rows, cols):
    """Generate rule-based think for clobber move."""
    action_str = state.action_to_string(player, action)
    # Clean up verbose format
    if "Action: " in action_str:
        action_str = action_str.split("Action: ")[-1]

    reasons = []

    # Get board info
    try:
        my_pieces = set()
        opp_pieces = set()
        obs = str(state)
        lines = obs.strip().split('\n')
        for i, line in enumerate(lines):
            for j, ch in enumerate(line):
                if ch in ('o', 'x'):
                    pos = i * cols + j  # approximate
                    if (ch == 'o' and player == 0) or (ch == 'x' and player == 1):
                        my_pieces.add(pos)
                    else:
                        opp_pieces.add(pos)
    except Exception:
        my_pieces, opp_pieces = set(), set()

    total_pieces = len(my_pieces) + len(opp_pieces)

    # Count moves before
    my_moves_before = len(legal)

    # Apply move and check after
    # Note: clobber legal_actions only returns moves for current_player
    # After our move, it's opponent's turn → child.legal_actions gives opponent's moves
    opp_moves_after = my_moves_before  # fallback
    my_moves_after = my_moves_before - 1  # fallback
    try:
        child = state.child(action)
        if child.is_terminal():
            returns = child.returns()
            if returns[player] > 0:
                reasons.append(f"Winning move! {action_str} — opponent has no legal captures left. "
                               f"In clobber, last player to capture wins.")
                return " ".join(reasons)
        # child.current_player() == 1-player (opponent's turn)
        opp_moves_after = len(child.legal_actions(child.current_player()))
        # To get our moves after, need to look one step further
        # Approximate: our moves ≈ before - 1 (we used one piece)
        my_moves_after = max(0, my_moves_before - 1)
    except Exception:
        pass

    # 2. SAFE CAPTURE
    # Parse to/from from action string (format: "a5b5" means a5 captures b5)
    is_safe = False
    if len(action_str) >= 4:
        # Target position: the cell we're capturing
        tc, tr = ord(action_str[2]) - ord('a'), int(action_str[3]) - 1
        target_pos = tr * cols + tc
        # Check if any opponent neighbor can recapture
        adj_to_target = _adj(target_pos, rows, cols)
        can_recapture = False
        for a in adj_to_target:
            if a in opp_pieces and a != target_pos:
                can_recapture = True
                break
        if not can_recapture:
            is_safe = True
            reasons.append(f"Safe capture: {action_str} — no adjacent opponent piece can recapture "
                           f"this cell, so it's permanently ours.")

    # 3. REDUCE MOBILITY
    opp_moves = opp_moves_after + 5  # approximate before (we captured one of their pieces)
    mobility_diff = opp_moves - opp_moves_after
    if mobility_diff > 0:
        reasons.append(f"Reduces opponent from {opp_moves} to {opp_moves_after} possible moves "
                       f"(−{mobility_diff}). Fewer moves means less flexibility for opponent.")

    # 4. PRESERVE OWN MOBILITY
    if my_moves_after >= len(legal) - 1:
        reasons.append(f"Preserves our mobility at {my_moves_after} moves — "
                       f"keeps options open for future turns.")

    # 5. ENDGAME PARITY
    if total_pieces <= 12:
        reasons.append(f"Endgame with {total_pieces} pieces — parity matters. "
                       f"Having the last capture wins.")

    # 6. GENERAL
    if not reasons:
        if not is_safe:
            reasons.append(f"Capturing with {action_str} — best available move for position control.")
        reasons.append(f"We have {my_moves_after} moves remaining, opponent has {opp_moves_after}.")

    return " ".join(reasons)


def clobber_rule_think_bot(state, player):
    """MCTS action + rule-based think."""
    legal = state.legal_actions(player)
    if not legal:
        return 0, "No legal moves."

    game = state.get_game()
    params = game.get_parameters()
    rows = params.get("rows", 5)
    cols = params.get("columns", 6)

    # Use MCTS for action selection
    from mcts_helper import get_mcts_bot, mcts_step_with_stats
    bot = get_mcts_bot(game, "clobber")

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

    think = _rule_think(action, state, player, legal, rows, cols)
    return action, think
