"""Shared MCTS bot factory. Use GAME_GEN_MODE=1 for fast data generation."""

import os
import numpy as np

# When GAME_GEN_MODE=1, reduce sim counts for fast generation (vs random)
_GEN_MODE = os.environ.get("GAME_GEN_MODE") == "1"

# Full strength (for testing vs MCTS) and gen mode (for data generation vs random)
CONFIGS = {
    "othello":    {"sim": 3000, "roll": 20, "gen_sim": 300, "gen_roll": 5},
    "hex":        {"sim": 3000, "roll": 50, "gen_sim": 300, "gen_roll": 10},
    "clobber":    {"sim": 5000, "roll": 20, "gen_sim": 500, "gen_roll": 5},
    "gin_rummy":  {"sim": 2000, "roll": 20, "gen_sim": 200, "gen_roll": 5},
    "liars_dice": {"sim": 10000, "roll": 50, "gen_sim": 1000, "gen_roll": 10},
}

_bots = {}


def get_mcts_bot(game, game_name):
    """Get or create MCTS bot for the given game. Respects GAME_GEN_MODE."""
    global _bots
    if game_name in _bots:
        return _bots[game_name]

    cfg = CONFIGS.get(game_name)
    if not cfg:
        return None

    sim = cfg["gen_sim"] if _GEN_MODE else cfg["sim"]
    roll = cfg["gen_roll"] if _GEN_MODE else cfg["roll"]

    try:
        from open_spiel.python.algorithms import mcts as mcts_lib

        class Evaluator(mcts_lib.Evaluator):
            def __init__(self, n_rollouts):
                self._n = n_rollouts
                self._rs = np.random.RandomState(42)

            def evaluate(self, state):
                if state.is_terminal():
                    return state.returns()
                t = np.zeros(state.num_players())
                for _ in range(self._n):
                    ws = state.clone()
                    while not ws.is_terminal():
                        a = ws.legal_actions()
                        if not a:
                            break
                        ws.apply_action(self._rs.choice(a))
                    t += ws.returns()
                return t / self._n

            def prior(self, state):
                la = state.legal_actions()
                return [(a, 1.0 / len(la)) for a in la] if la else []

        bot = mcts_lib.MCTSBot(
            game=game, uct_c=1.414, max_simulations=sim,
            evaluator=Evaluator(n_rollouts=roll),
            random_state=np.random.RandomState(hash(game_name) % 2**31),
            solve=True,
        )
        _bots[game_name] = bot
        return bot
    except Exception:
        return None
