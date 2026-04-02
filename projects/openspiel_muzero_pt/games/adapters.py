from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .action_codecs import ActionCodec, get_action_codec
from .encoders import build_state_encoder
from .game_spec import GameSpec


def _require_pyspiel():
    import pyspiel

    return pyspiel


@dataclass(slots=True)
class EncodedGameState:
    obs: np.ndarray
    legal_mask: np.ndarray
    phase: float
    current_player: int
    move_index: int
    terminal: bool


class RandomRolloutEvaluator:
    def __init__(self, n_rollouts: int, seed: int = 0):
        self.n_rollouts = max(int(n_rollouts), 1)
        self.random_state = np.random.RandomState(seed)

    def evaluate(self, state):
        if state.is_terminal():
            return state.returns()
        total = np.zeros(state.num_players(), dtype=np.float32)
        for _ in range(self.n_rollouts):
            working = state.clone()
            while not working.is_terminal():
                legal = working.legal_actions()
                if not legal:
                    break
                working.apply_action(int(self.random_state.choice(legal)))
            total += np.asarray(working.returns(), dtype=np.float32)
        return total / float(self.n_rollouts)

    def prior(self, state):
        legal = state.legal_actions()
        if not legal:
            return []
        probability = 1.0 / float(len(legal))
        return [(int(action), probability) for action in legal]


class AffineOpenSpielAdapter:
    def __init__(self, spec: GameSpec):
        self.spec = spec
        self.codec: ActionCodec = get_action_codec(spec)
        self.state_encoder = build_state_encoder(spec)
        self.pyspiel = _require_pyspiel()

    def build_game(self):
        return self.pyspiel.load_game(self.spec.game_name, dict(self.spec.game_params))

    def new_initial_state(self):
        return self.build_game().new_initial_state()

    def clone_from_history(self, history_actions: list[int]):
        state = self.new_initial_state()
        for action in history_actions:
            state.apply_action(self.codec.decode_dense(int(action), self.spec))
        return state

    def encode_state(self, state) -> EncodedGameState:
        obs = self.state_encoder.encode(state)
        legal_mask = self.legal_action_mask(state)
        move_index = self._move_index(state)
        phase = self.spec.phase_ratio(move_index)
        obs[4].fill(phase)
        return EncodedGameState(
            obs=obs.astype(np.float32, copy=False),
            legal_mask=legal_mask.astype(np.float32, copy=False),
            phase=phase,
            current_player=int(state.current_player()) if not state.is_terminal() else -1,
            move_index=move_index,
            terminal=bool(state.is_terminal()),
        )

    def legal_action_mask(self, state) -> np.ndarray:
        mask = np.zeros((self.spec.action_dim,), dtype=np.float32)
        if state.is_terminal():
            return mask
        current_player = int(state.current_player())
        for action in state.legal_actions(current_player):
            dense = self.codec.encode_dense(int(action), self.spec)
            if 0 <= dense < self.spec.action_dim:
                mask[dense] = 1.0
        return mask

    def legal_actions_dense(self, state) -> list[int]:
        if state.is_terminal():
            return []
        current_player = int(state.current_player())
        return [self.codec.encode_dense(int(action), self.spec) for action in state.legal_actions(current_player)]

    def apply_dense_action(self, state, action_id: int) -> None:
        state.apply_action(self.codec.decode_dense(int(action_id), self.spec))

    def create_affine_mcts_bot(self, seed: int = 0, *, simulations: int | None = None, rollouts: int | None = None):
        from open_spiel.python.algorithms import mcts as mcts_lib

        return mcts_lib.MCTSBot(
            game=self.build_game(),
            uct_c=1.414,
            max_simulations=int(simulations or self.spec.baseline_max_simulations),
            evaluator=RandomRolloutEvaluator(n_rollouts=int(rollouts or self.spec.baseline_n_rollouts), seed=seed),
            random_state=np.random.RandomState(seed + 1),
            solve=True,
        )

    def current_player_view_value(self, state, player: int) -> float:
        if not state.is_terminal():
            raise ValueError("Value is only exact on terminal states")
        returns = state.returns()
        return float(returns[int(player)])

    def current_player_reward(self, state_before, state_after, player: int) -> float:
        if not state_after.is_terminal():
            return 0.0
        returns = state_after.returns()
        return float(returns[int(player)])

    def _move_index(self, state) -> int:
        move_number = getattr(state, "move_number", None)
        if callable(move_number):
            try:
                return int(move_number())
            except Exception:
                pass
        history = getattr(state, "history", None)
        if callable(history):
            try:
                return len(history())
            except Exception:
                pass
        history_str = str(state)
        return history_str.count(" x ") + history_str.count(" o ")
