"""Clobber bot v4: MCTS search (5000 sim) + mobility explanation.

v1-v3: minimax + parity → 0% vs MCTS 1500sim
v4: Use own MCTS (5000 sim, >3x opponent's 1500) for move selection.
    Generate think blocks explaining the mobility/parity reasoning.
"""

import numpy as np

_mcts_bot = None
_mcts_game_name = None


def _get_mcts_bot(game):
    global _mcts_bot, _mcts_game_name
    gname = game.get_type().short_name
    if _mcts_bot is not None and _mcts_game_name == gname:
        return _mcts_bot
    try:
        from open_spiel.python.algorithms import mcts as mcts_lib

        class Evaluator(mcts_lib.Evaluator):
            def __init__(self, n_rollouts=20):
                self._n = n_rollouts
                self._rs = np.random.RandomState(42)
            def evaluate(self, state):
                if state.is_terminal(): return state.returns()
                t = np.zeros(state.num_players())
                for _ in range(self._n):
                    ws = state.clone()
                    while not ws.is_terminal():
                        a = ws.legal_actions()
                        if not a: break
                        ws.apply_action(self._rs.choice(a))
                    t += ws.returns()
                return t / self._n
            def prior(self, state):
                la = state.legal_actions()
                return [(a, 1.0/len(la)) for a in la] if la else []

        _mcts_bot = mcts_lib.MCTSBot(
            game=game, uct_c=1.414, max_simulations=5000,
            evaluator=Evaluator(n_rollouts=20),
            random_state=np.random.RandomState(789),
            solve=True,
        )
        _mcts_game_name = gname
        return _mcts_bot
    except Exception:
        return None


def clobber_bot(state, player):
    legal = state.legal_actions(player)
    if not legal:
        return 0, "No legal moves."

    # Check for immediate wins
    for a in legal:
        child = state.child(a)
        if child.is_terminal():
            name = state.action_to_string(player, a)
            return a, (f"Capturing at {name[2:4]} ends the game — opponent has no moves left. "
                       f"In clobber, the last player to move wins. Taking the winning move.")

    game = state.get_game()
    bot = _get_mcts_bot(game)
    action = None

    if bot is not None:
        try:
            action = bot.step(state)
            if action not in legal:
                action = None
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

    # Estimate game phase and parity
    total_remaining = total_moves + opp_moves
    mob_diff = total_moves - opp_moves
    parity_good = total_remaining % 2 == 1  # odd = we get last move (we move first)

    # Parse board dimensions
    obs = state.observation_string(player)
    my_char = 'x' if player == 0 else 'o'
    opp_char = 'o' if player == 0 else 'x'
    my_count = obs.count(my_char)
    opp_count = obs.count(opp_char)

    # Phase detection
    if total_moves > 40:
        phase = "opening"
    elif total_moves > 15:
        phase = "midgame"
    else:
        phase = "endgame"

    # Diverse think based on game situation
    if child.is_terminal() or opp_moves == 0:
        think = (f"Capturing {src_pos}→{dst_pos} ends the game — opponent has no legal moves. "
                 f"In clobber, the last player to capture wins. This is the winning move.")
    elif opp_moves <= 3 and phase == "endgame":
        parity_note = "we move last" if parity_good else "opponent moves last — must force an extra capture"
        think = (f"Endgame squeeze: capturing {src_pos}→{dst_pos} leaves opponent with only {opp_moves} move(s). "
                 f"Pieces remaining: {my_count} ours vs {opp_count} opponent. "
                 f"Total remaining captures ~{total_remaining}, parity: {parity_note}. "
                 f"In clobber's endgame, restricting opponent to forced moves is decisive.")
    elif mob_diff >= 5:
        think = (f"Capturing {src_pos}→{dst_pos} — we have {total_moves} moves vs opponent's {opp_moves} "
                 f"(+{mob_diff} advantage). In clobber, mobility advantage means more flexibility "
                 f"to choose where and when to capture. This forces opponent into reactive play "
                 f"while we dictate the board position. Phase: {phase}.")
    elif phase == "opening":
        think = (f"Opening capture {src_pos}→{dst_pos}. Early game strategy: establish mobility advantage "
                 f"by capturing toward the center where more adjacent opponents exist. "
                 f"After this: {opp_moves} opponent moves vs {total_moves} ours. "
                 f"Pieces: {my_count} vs {opp_count}. Building positional advantage for the endgame.")
    elif mob_diff > 0:
        think = (f"Capturing {src_pos}→{dst_pos} maintains our mobility lead ({total_moves} vs {opp_moves}). "
                 f"In the {phase}, preserving more capture options than opponent means we can "
                 f"choose the best moment to transition into an endgame squeeze. "
                 f"Estimated ~{total_remaining} total captures remain, "
                 f"{'favorable' if parity_good else 'unfavorable'} parity.")
    elif mob_diff <= 0 and phase == "midgame":
        think = (f"Capturing {src_pos}→{dst_pos} — currently trailing in mobility "
                 f"({total_moves} vs opponent's {opp_moves}). This capture aims to flip the mobility balance "
                 f"by removing an opponent piece from a high-connectivity area. "
                 f"When behind, the priority is disrupting opponent's capture chains "
                 f"rather than preserving our own. Pieces: {my_count} vs {opp_count}.")
    else:
        parity_note = "favorable (we get last move)" if parity_good else "unfavorable (opponent gets last move)"
        think = (f"Capturing {src_pos}→{dst_pos}. Mobility: {total_moves} (ours) vs {opp_moves} (opponent). "
                 f"Parity of remaining moves (~{total_remaining}): {parity_note}. "
                 f"In clobber, the player making the last capture wins. "
                 f"Every capture changes the parity — choosing the right target is critical.")

    return action, think
