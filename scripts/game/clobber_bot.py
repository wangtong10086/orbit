"""Clobber bot v5: Rule-based strategy think + MCTS action.

6 core rules encoded as IF-THEN patterns:
Rule 1: SAFE CAPTURE — capture where opponent can't immediately recapture
Rule 2: AVOID CHAIN — don't give opponent a sequence of forced recaptures
Rule 3: FRAGMENT — split board into isolated regions to limit opponent options
Rule 4: REDUCE MOBILITY — minimize opponent's legal moves
Rule 5: PRESERVE OWN MOBILITY — keep our future options open
Rule 6: ENDGAME PARITY — last mover wins, count remaining moves
"""

from mcts_helper import get_mcts_bot, mcts_step_with_stats, format_mcts_think


def _parse_board_grid(state, player):
    """Parse board into grid for adjacency analysis."""
    obs = state.observation_string(player)
    my_char = 'x' if player == 0 else 'o'
    opp_char = 'o' if player == 0 else 'x'
    my_pieces = set()
    opp_pieces = set()
    rows, cols = 0, 0
    r = 0
    for line in obs.split('\n'):
        c = 0
        has_piece = False
        for ch in line:
            if ch in ('x', 'o', '.'):
                pos = r * 100 + c
                if ch == my_char:
                    my_pieces.add(pos)
                elif ch == opp_char:
                    opp_pieces.add(pos)
                c += 1
                has_piece = True
        if has_piece:
            cols = max(cols, c)
            r += 1
    rows = r
    return my_pieces, opp_pieces, rows, cols


def _orthogonal_neighbors(pos, rows, cols):
    r, c = pos // 100, pos % 100
    nbrs = []
    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < cols:
            nbrs.append(nr * 100 + nc)
    return nbrs


def _can_recapture(dst_pos, my_pieces_after, opp_pieces_after, rows, cols):
    """Check if opponent can immediately recapture our piece at dst_pos."""
    for n in _orthogonal_neighbors(dst_pos, rows, cols):
        if n in opp_pieces_after:
            return True
    return False


def _count_opp_chain(dst_pos, my_pieces_after, opp_pieces_after, rows, cols):
    """Count actual recapture threat: opponent pieces that can capture our piece at dst_pos,
    and then how many of OUR pieces can recapture them (chain depth)."""
    # Only count opponent pieces directly adjacent to dst_pos (can recapture us)
    direct_threats = [n for n in _orthogonal_neighbors(dst_pos, rows, cols)
                     if n in opp_pieces_after]
    if not direct_threats:
        return 0
    # For each threat, check if capturing us would expose them to our recapture
    chain = len(direct_threats)
    return chain


def _count_regions(pieces, rows, cols):
    """Count connected components of a set of pieces."""
    if not pieces:
        return 0
    visited = set()
    regions = 0
    for start in pieces:
        if start in visited:
            continue
        regions += 1
        q = [start]
        while q:
            p = q.pop()
            if p in visited:
                continue
            visited.add(p)
            for n in _orthogonal_neighbors(p, rows, cols):
                if n in pieces and n not in visited:
                    q.append(n)
    return regions


def _clobber_candidate_label(action, state, player, my_pieces, opp_pieces, rows, cols):
    """Quick label for candidate annotation."""
    name = state.action_to_string(player, action)
    if "Action: " in name:
        name = name.split("Action: ")[-1]
    try:
        dst_pos = name[2:4] if len(name) >= 4 else name
        dst_r, dst_c = ord(dst_pos[0]) - ord('a'), int(dst_pos[1]) - 1
        dst_p = dst_c * 100 + dst_r
        src_pos = name[:2]
        src_r, src_c = ord(src_pos[0]) - ord('a'), int(src_pos[1]) - 1
        src_p = src_c * 100 + src_r
        my_after = (my_pieces - {src_p}) | {dst_p}
        opp_after = opp_pieces - {dst_p}
        if not _can_recapture(dst_p, my_after, opp_after, rows, cols):
            return "safe"
        return "unsafe"
    except Exception:
        return "capture"


def _get_game_context(action, state, player):
    """Get game-specific context for EVERY action."""
    my_pieces, opp_pieces, rows, cols = _parse_board_grid(state, player)
    name = state.action_to_string(player, action)
    if "Action: " in name:
        name = name.split("Action: ")[-1]

    src_pos = name[:2] if len(name) >= 4 else name
    dst_pos = name[2:4] if len(name) >= 4 else name

    try:
        src_r, src_c = ord(src_pos[0]) - ord('a'), int(src_pos[1]) - 1
        dst_r, dst_c = ord(dst_pos[0]) - ord('a'), int(dst_pos[1]) - 1
        src_p = src_c * 100 + src_r
        dst_p = dst_c * 100 + dst_r
        my_after = (my_pieces - {src_p}) | {dst_p}
        opp_after = opp_pieces - {dst_p}
    except Exception:
        return f"{name}."

    parts = [f"{name}."]

    # Safe capture — objective fact
    recapturable = _can_recapture(dst_p, my_after, opp_after, rows, cols)
    if not recapturable:
        parts.append("Safe capture.")
    else:
        parts.append("Opponent can recapture.")

    # Mobility change — just the numbers
    try:
        child = state.child(action)
        if child.is_terminal():
            return f"{name}. Winning move."
        opp_moves_after = len(child.legal_actions(child.current_player()))
        parts.append(f"Opponent moves ->{opp_moves_after}.")
    except Exception:
        pass

    # Endgame
    total = len(my_pieces) + len(opp_pieces)
    if total <= 12:
        parts.append(f"Endgame ({total} pieces, parity matters).")

    return " ".join(parts)


def clobber_bot(state, player):
    legal = state.legal_actions(player)
    if not legal:
        return 0, "No legal moves."

    # Check for immediate wins
    for a in legal:
        child = state.child(a)
        if child.is_terminal():
            name = state.action_to_string(player, a)
            return a, (f"Rule: WINNING MOVE. Capturing {name[2:4]} ends the game — "
                       f"opponent has no moves left. In clobber, last to capture wins.")

    game = state.get_game()
    bot = get_mcts_bot(game, "clobber")
    action = None
    mcts_stats = []

    if bot is not None:
        try:
            action, mcts_stats, root = mcts_step_with_stats(bot, state)
            if action not in legal:
                action = None
                mcts_stats = []
        except Exception:
            action = None

    if action is None:
        action = legal[0]

    name = state.action_to_string(player, action)
    src_pos = name[:2] if len(name) >= 4 else name
    dst_pos = name[2:4] if len(name) >= 4 else name
    total_moves = len(legal)

    child = state.child(action)
    if not child.is_terminal():
        cp = child.current_player()
        opp_moves = len(child.legal_actions(cp)) if cp >= 0 else 0
    else:
        opp_moves = 0

    # Parse board for advanced analysis
    my_pieces, opp_pieces, rows, cols = _parse_board_grid(state, player)
    obs = state.observation_string(player)
    my_char = 'x' if player == 0 else 'o'
    opp_char = 'o' if player == 0 else 'x'
    my_count = obs.count(my_char)
    opp_count = obs.count(opp_char)

    # If we have MCTS stats, annotate candidates + format think
    if mcts_stats:
        annotated = []
        for a, name, visits, wr in mcts_stats:
            label = _clobber_candidate_label(a, state, player, my_pieces, opp_pieces, rows, cols)
            annotated.append((a, f"{name} [{label}]", visits, wr))
        context = _get_game_context(action, state, player)
        think = format_mcts_think(annotated, state, player, context, root)
        if think is not None:
            return action, think
        # Shallow search — fall through to game-specific think below

    # Fallback: rule-based think (when MCTS stats unavailable)
    total_remaining = total_moves + opp_moves
    mob_diff = total_moves - opp_moves
    parity_good = total_remaining % 2 == 1

    # Phase
    if total_moves > 40:
        phase = "opening"
    elif total_moves > 15:
        phase = "midgame"
    else:
        phase = "endgame"

    # Advanced analysis: simulate the capture
    # Parse src/dst from action name to get positions
    src_r, src_c = ord(src_pos[0]) - ord('a'), int(src_pos[1]) - 1
    dst_r, dst_c = ord(dst_pos[0]) - ord('a'), int(dst_pos[1]) - 1
    src_p = src_c * 100 + src_r
    dst_p = dst_c * 100 + dst_r

    # After capture: our piece moves from src to dst, opponent's piece at dst removed
    my_after = (my_pieces - {src_p}) | {dst_p}
    opp_after = opp_pieces - {dst_p}

    recapturable = _can_recapture(dst_p, my_after, opp_after, rows, cols)
    opp_chain = _count_opp_chain(dst_p, my_after, opp_after, rows, cols)
    opp_regions_before = _count_regions(opp_pieces, rows, cols)
    opp_regions_after = _count_regions(opp_after, rows, cols)
    fragmented = opp_regions_after > opp_regions_before

    # --- RULE-BASED THINK ---

    # RULE 1: SAFE CAPTURE
    if not recapturable and opp_chain == 0:
        parts = [f"Rule: SAFE CAPTURE. {src_pos}→{dst_pos} — after this capture, "
                f"our piece at {dst_pos} has no adjacent opponent pieces, "
                f"so opponent cannot immediately recapture. This is ideal: "
                f"we remove an opponent piece without exposing ourselves."]
        if fragmented:
            parts.append(f"Bonus: this splits opponent's pieces into {opp_regions_after} "
                        f"separate groups (was {opp_regions_before}), limiting their coordination.")
        parts.append(f"Mobility: {total_moves} ours vs {opp_moves} opponent. "
                    f"Pieces: {my_count} vs {opp_count}.")
        return action, " ".join(parts)

    # RULE 2: AVOID CHAIN (only when real threat, not normal adjacency)
    if opp_chain >= 3 and phase != "opening":
        return action, (f"Rule: CHAIN AWARENESS. {src_pos}→{dst_pos} — "
                       f"opponent has {opp_chain} pieces nearby that could form a recapture chain. "
                       f"However, deep search confirms this is still the best option. "
                       f"The alternative moves are worse — sometimes accepting a small chain "
                       f"is necessary to maintain overall board position. "
                       f"Key: we retain {total_moves} options vs opponent's {opp_moves}. "
                       f"Pieces: {my_count} vs {opp_count}.")

    # RULE 3: FRAGMENT
    if fragmented:
        return action, (f"Rule: FRAGMENT BOARD. {src_pos}→{dst_pos} splits opponent's pieces "
                       f"from {opp_regions_before} group(s) into {opp_regions_after}. "
                       f"Isolated groups can't coordinate captures — each small group "
                       f"runs out of moves faster. This is how we create local advantages. "
                       f"Opponent has {opp_moves} moves remaining. "
                       f"Pieces: {my_count} vs {opp_count}.")

    # RULE 4: REDUCE OPPONENT MOBILITY
    if opp_moves < total_moves and mob_diff >= 3:
        return action, (f"Rule: REDUCE MOBILITY. {src_pos}→{dst_pos} leaves opponent with {opp_moves} moves "
                       f"vs our {total_moves} (+{mob_diff}). "
                       f"In clobber, the player with more options controls the game — "
                       f"opponent is forced into increasingly bad captures while we choose freely. "
                       f"{'Recapturable, but the mobility advantage outweighs the risk.' if recapturable else ''} "
                       f"Pieces: {my_count} vs {opp_count}. Phase: {phase}.")

    # RULE 5: PRESERVE OWN MOBILITY
    if total_moves >= opp_moves and phase != "endgame":
        # Check if this move preserves our future options
        return action, (f"Rule: PRESERVE MOBILITY. {src_pos}→{dst_pos} — "
                       f"maintaining {total_moves} capture options. "
                       f"Good clobber is not about capturing the most — it's about "
                       f"being the last player who CAN capture. "
                       f"{'This capture is safe from recapture.' if not recapturable else 'Opponent can recapture, but our position remains flexible.'} "
                       f"Opponent has {opp_moves} moves. Regions: {opp_regions_after}. "
                       f"Pieces: {my_count} vs {opp_count}.")

    # RULE 6: ENDGAME PARITY
    if phase == "endgame":
        parity_note = "we get the last move" if parity_good else "opponent gets last move"
        return action, (f"Rule: ENDGAME PARITY. {src_pos}→{dst_pos} with {total_remaining} total captures left. "
                       f"Parity: {parity_note}. "
                       f"{'Favorable — maintain parity by making safe captures.' if parity_good else 'Unfavorable — must force an extra capture to flip parity.'} "
                       f"Opponent has {opp_moves} moves. In endgame, every single capture "
                       f"changes who gets the last move. "
                       f"Pieces: {my_count} vs {opp_count}.")

    # DEFAULT
    return action, (f"Capturing {src_pos}→{dst_pos}. Mobility: {total_moves} vs {opp_moves}. "
                   f"{'Safe from recapture.' if not recapturable else 'Opponent can recapture.'} "
                   f"Opponent regions: {opp_regions_after}. "
                   f"Parity {'favorable' if parity_good else 'unfavorable'}. "
                   f"Pieces: {my_count} vs {opp_count}. Phase: {phase}.")
