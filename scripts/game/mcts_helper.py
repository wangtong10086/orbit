"""Shared MCTS bot factory + search-based think generation.

Key innovation: extract MCTS search tree statistics to generate think chains
that faithfully represent the actual decision process:
  "Evaluated N options: d3 (49% win, 336 visits), c4 (48%, 262)...
   d3 has highest win rate. Choosing d3."
"""

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


def mcts_step_with_stats(bot, state):
    """Run MCTS search and return (best_action, child_stats, root_node).

    child_stats: list of (action, action_name, visits, win_rate) sorted by visits desc.
    root_node: the MCTS SearchNode root (for deeper lookahead).
    """
    try:
        root = bot.mcts_search(state)
        player = state.current_player()

        stats = []
        for child in root.children:
            a = child.action
            name = state.action_to_string(player, a)
            # Clean up verbose action names (e.g., "Player: 1 Action: Draw upcard" → "Draw upcard")
            if "Action: " in name:
                name = name.split("Action: ")[-1]
            visits = child.explore_count
            value = child.total_reward / max(visits, 1)
            wr = max(0, min(100, 50 + value * 50))  # clamp to 0-100%
            stats.append((a, name, visits, wr))

        # Sort by visits (MCTS picks highest visit count)
        stats.sort(key=lambda x: -x[2])
        best_action = stats[0][0] if stats else state.legal_actions(player)[0]

        return best_action, stats, root
    except Exception:
        # Fallback: use step() without stats
        action = bot.step(state)
        return action, [], None


def format_mcts_think(stats, state, player, game_context="", root=None):
    """Generate think chain from MCTS search statistics.

    Includes:
    1. All evaluated options with win rates
    2. Why the best was chosen
    3. Lookahead: opponent's likely response and our counter (from search tree)
    4. Game-specific context

    game_context: optional game-specific insight
    root: MCTS root SearchNode (for deeper lookahead)
    """
    if not stats:
        return "Taking best available move."

    n = len(stats)
    best_a, best_name, best_visits, best_wr = stats[0]
    total_visits = sum(v for _, _, v, _ in stats)

    parts = []

    # 1. Show all evaluated options (up to 5)
    option_strs = []
    for a, name, visits, wr in stats[:5]:
        pct = visits * 100 // max(total_visits, 1)
        option_strs.append(f"{name} ({wr:.0f}%, {visits} visits)")
    if n > 5:
        option_strs.append(f"...{n - 5} more")
    parts.append(f"Evaluated {n} options: {', '.join(option_strs)}.")

    # 2. Why best was chosen
    if len(stats) >= 2:
        second_name = stats[1][1]
        second_wr = stats[1][3]
        gap = best_wr - second_wr
        if gap > 10:
            parts.append(f"{best_name} is clearly best (+{gap:.0f}% over {second_name}).")
        elif gap > 3:
            parts.append(f"{best_name} edges out {second_name} by {gap:.0f}%.")
        else:
            parts.append(f"{best_name} slightly ahead of {second_name} ({best_wr:.0f}% vs {second_wr:.0f}%).")
    else:
        parts.append(f"{best_name} is the only viable option.")

    # 3. Lookahead from search tree (opponent response → our counter)
    if root is not None:
        try:
            # Find the best child node
            best_child = None
            for child in root.children:
                if child.action == best_a:
                    best_child = child
                    break
            if best_child and best_child.children:
                # Opponent's most likely response
                opp_responses = sorted(best_child.children, key=lambda c: -c.explore_count)
                if opp_responses:
                    opp = opp_responses[0]
                    opp_name = state.child(best_a).action_to_string(1 - player, opp.action)
                    opp_visits = opp.explore_count

                    lookahead = f"If I play {best_name}, opponent most likely responds {opp_name} ({opp_visits} visits)."

                    # Our counter to opponent's response
                    if opp.children:
                        counters = sorted(opp.children, key=lambda c: -c.explore_count)
                        if counters:
                            counter = counters[0]
                            opp_state = state.child(best_a).child(opp.action)
                            counter_name = opp_state.action_to_string(player, counter.action)
                            counter_wr = 50 + (counter.total_reward / max(counter.explore_count, 1)) * 50
                            lookahead += f" Then I play {counter_name} ({counter_wr:.0f}% win)."
                    parts.append(lookahead)
        except Exception:
            pass  # Lookahead is optional — don't fail on it

    # 4. Game-specific context
    if game_context:
        parts.append(game_context)

    parts.append(f"Choosing {best_name}.")
    return " ".join(parts)
