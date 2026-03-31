"""Self-play training for GAME policy models."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import multiprocessing as mp
from pathlib import Path
import random
import shutil
import time

import numpy as np

from forge.data.game_generators.policy_generators import (
    LoadedPolicySnapshot,
    build_policy_snapshot,
    load_policy_snapshot,
)
from forge.data.game_policy_models.artifacts import (
    PERFECT_INFO_GAMES,
    PERFECT_INFO_TEACHER_BUDGETS,
    RECENT_REPLAY_FRACTION,
    REPLAY_WINDOW_ROUNDS,
    REPLAY_WINDOW_ROWS,
    _arena_path,
    _autotune_path,
    _best_dir,
    _ensure_dirs,
    _gpu_snapshot,
    _history_dir,
    _latest_dir,
    _load_json,
    _load_status,
    _policy_repo_id,
    _promote_latest_to_best,
    _replay_meta_path,
    _replay_path,
    _runtime_profile,
    _save_heartbeat,
    _save_json,
    _save_status,
    sync_selfplay_artifacts_to_hf,
    restore_selfplay_artifacts_from_hf,
)
from forge.data.game_policy_models.contracts import (
    ArenaEvalReport,
    ReplayBufferReport,
    SelfPlayHeartbeat,
    SelfPlayLongRunReport,
    SelfPlayStatusState,
    SelfPlayTrainReport,
)
from forge.data.game_policy_models.selfplay_control import (
    _cheap_teacher_threshold,
    _make_arena_report,
    _phase_name,
    _phase_simulations,
    _required_wins_for_threshold,
)
from forge.data.game_policy_models.selfplay_runtime import (
    _NeuralSearchEvaluator,
    _ProcessSharedSearchEvaluator,
    _SharedBatchedPredictor,
    _SharedSearchEvaluator,
    _load_checkpoint_dir,
    _build_process_predictor_pool,
    _build_shared_predictor_pool,
    _init_process_predictor_clients,
    _materialize_replay_model,
    _normalize_policy,
    _process_predictor_client,
    _shared_predictor_batch_size,
    _shared_predictor_latency_ms,
    _state_key,
)
from forge.data.game_policy_models.featurizers import extract_state_features, feature_spec_for_game, feature_spec_for_state, legal_action_mask
from forge.data.game_policy_models.game_runtime import load_game_runtime_symbols
from forge.data.game_policy_models.models import PolicyModelArtifact, build_policy_model_module, default_selfplay_model_config, extract_policy_logits, extract_value_predictions, load_policy_model
from forge.data.game_trajectory_generators import resolve_game_trajectory_generator


@dataclass
class _ReplayRow:
    features: np.ndarray
    legal_mask: np.ndarray
    policy_target: np.ndarray
    value_target: float
    player_id: int
    game_step: int
    episode_id: int
    state_key: str


def _require_torch():
    try:
        import torch
        from torch.utils.data import DataLoader, TensorDataset
    except ImportError as exc:
        raise RuntimeError(
            "GAME self-play training requires PyTorch. Install `torch` on the active environment or rental first."
        ) from exc
    return torch, DataLoader, TensorDataset


def _require_search():
    try:
        import pyspiel
    except ImportError as exc:
        raise RuntimeError(
            "GAME self-play training requires open_spiel with python bindings available."
        ) from exc
    return pyspiel


def _game_runtime() -> dict[str, object]:
    return load_game_runtime_symbols()


@dataclass
class _SearchChild:
    action: int
    prior: float
    visit_count: int = 0
    value_sum: float = 0.0

    @property
    def q_value(self) -> float:
        return self.value_sum / self.visit_count if self.visit_count else 0.0


class _BaseRootSearch:
    family = "search"

    def __init__(self, *, evaluator: "_NeuralSearchEvaluator", simulations: int, root_noise: bool = True):
        self.evaluator = evaluator
        self.simulations = max(int(simulations), 2)
        self.root_noise = root_noise

    def policy(self, state, *, root_player: int) -> np.ndarray:
        raise NotImplementedError

    def _children(self, state) -> tuple[list[_SearchChild], np.ndarray]:
        action_dim = int(state.get_game().num_distinct_actions())
        mask = legal_action_mask(state.get_game(), state, state.current_player())
        priors = np.zeros(action_dim, dtype=np.float32)
        for action, prob in self.evaluator.prior(state):
            if 0 <= int(action) < action_dim:
                priors[int(action)] = float(prob)
        priors = _normalize_policy(priors, mask)
        if self.root_noise:
            priors = _apply_dirichlet_noise(priors, mask)
        children = [_SearchChild(action=action, prior=float(priors[action])) for action in np.flatnonzero(mask > 0)]
        return children, mask

    def _rollout(self, state, *, root_player: int, max_depth: int = 48) -> float:
        working = state.clone()
        rng = random.Random(abs(hash(str(working))) % (2**31))
        depth = 0
        while not working.is_terminal() and depth < max_depth:
            if working.is_chance_node():
                outcomes = working.chance_outcomes()
                working.apply_action(rng.choices([a for a, _ in outcomes], [p for _, p in outcomes])[0])
                depth += 1
                continue
            player_id = working.current_player()
            priors = self.evaluator.prior(working)
            if not priors:
                legal = working.legal_actions(player_id)
                action = rng.choice(legal)
            else:
                action = max(priors, key=lambda item: item[1])[0]
            working.apply_action(int(action))
            depth += 1
        if working.is_terminal():
            return _returns_to_value(list(working.returns()), root_player)
        values = self.evaluator.evaluate(working)
        return _returns_to_value(list(values), root_player)

    def _visit_policy(self, children: list[_SearchChild], mask: np.ndarray) -> np.ndarray:
        policy = np.zeros_like(mask, dtype=np.float32)
        for child in children:
            policy[int(child.action)] = float(child.visit_count)
        return _normalize_policy(policy, mask)


class PuctSearch(_BaseRootSearch):
    family = "puct"

    def __init__(self, *, evaluator: "_NeuralSearchEvaluator", simulations: int, c_puct: float = 1.5, root_noise: bool = True):
        super().__init__(evaluator=evaluator, simulations=simulations, root_noise=root_noise)
        self.c_puct = c_puct

    def policy(self, state, *, root_player: int) -> np.ndarray:
        children, mask = self._children(state)
        if not children:
            return _normalize_policy(np.zeros_like(mask, dtype=np.float32), mask)
        total_visits = 0
        for _ in range(self.simulations):
            selected = max(
                children,
                key=lambda child: child.q_value + self.c_puct * child.prior * ((total_visits + 1) ** 0.5) / (1 + child.visit_count),
            )
            next_state = state.clone()
            next_state.apply_action(int(selected.action))
            value = self._rollout(next_state, root_player=root_player)
            selected.visit_count += 1
            selected.value_sum += value
            total_visits += 1
        return self._visit_policy(children, mask)


@dataclass
class _PerfectInfoNode:
    prior: float
    to_play: int
    visit_count: int = 0
    value_sum: float = 0.0
    is_expanded: bool = False
    legal_mask: np.ndarray | None = None
    children: dict[int, "_PerfectInfoNode"] | None = None

    @property
    def q_value(self) -> float:
        return self.value_sum / self.visit_count if self.visit_count else 0.0


class PerfectInfoPuctSearch:
    family = "perfect_puct"

    def __init__(
        self,
        *,
        evaluator: "_NeuralSearchEvaluator",
        simulations: int,
        c_puct: float = 1.5,
        root_noise_alpha: float = 0.3,
        eval_batch_size: int = 16,
    ):
        self.evaluator = evaluator
        self.simulations = max(int(simulations), 2)
        self.c_puct = float(c_puct)
        self.root_noise_alpha = float(root_noise_alpha)
        self.eval_batch_size = max(int(eval_batch_size), 1)

    def policy(self, state, *, root_player: int) -> np.ndarray:
        action_dim = int(state.get_game().num_distinct_actions())
        root = _PerfectInfoNode(prior=1.0, to_play=root_player)
        self._expand(root, state, root_player=root_player, root_noise=True)
        remaining = self.simulations
        while remaining > 0:
            batch_take = min(self.eval_batch_size, remaining)
            pending_batch = [self._traverse(root, state.clone(), root_player=root_player) for _ in range(batch_take)]
            self._resolve_pending_batch(pending_batch, root_player=root_player)
            remaining -= batch_take
        policy = np.zeros(action_dim, dtype=np.float32)
        for action, child in (root.children or {}).items():
            policy[int(action)] = float(child.visit_count)
        legal_mask = root.legal_mask if root.legal_mask is not None else legal_action_mask(state.get_game(), state, root_player)
        return _normalize_policy(policy, legal_mask)

    def _predict_root_value(self, state, *, root_player: int, value: float) -> float:
        players = state.get_game().num_players()
        if players == 2:
            values = [value, -value] if state.current_player() == 0 else [-value, value]
        else:
            values = [0.0 for _ in range(players)]
            current_player = state.current_player()
            if current_player >= 0:
                values[current_player] = value
        return _returns_to_value(values, root_player)

    def _backup(self, path: list[_PerfectInfoNode], value: float) -> None:
        for item in path:
            item.visit_count += 1
            item.value_sum += value

    def _traverse(self, root: _PerfectInfoNode, state, *, root_player: int) -> dict[str, object]:
        node = root
        path = [root]
        while True:
            if state.is_terminal():
                return {
                    "path": path,
                    "terminal_value": _returns_to_value(list(state.returns()), root_player),
                }
            while state.is_chance_node():
                outcomes = state.chance_outcomes()
                state.apply_action(random.choices([a for a, _ in outcomes], [p for _, p in outcomes])[0])
                if state.is_terminal():
                    return {
                        "path": path,
                        "terminal_value": _returns_to_value(list(state.returns()), root_player),
                    }
            if not node.is_expanded:
                return {"path": path, "leaf_node": node, "leaf_state": state}
            action, child = self._select_child(node)
            state.apply_action(int(action))
            node = child
            path.append(node)

    def _expand_from_prediction(
        self,
        node: _PerfectInfoNode,
        state,
        *,
        root_player: int,
        priors: np.ndarray,
        value: float,
        root_noise: bool = False,
    ) -> float:
        current_player = state.current_player()
        node.to_play = current_player
        legal_mask = legal_action_mask(state.get_game(), state, current_player)
        normalized = _normalize_policy(priors, legal_mask)
        if root_noise:
            normalized = _apply_dirichlet_noise(normalized, legal_mask, alpha=self.root_noise_alpha)
        node.legal_mask = legal_mask
        node.children = {
            int(action): _PerfectInfoNode(prior=float(normalized[int(action)]), to_play=1 - current_player)
            for action in np.flatnonzero(legal_mask > 0)
        }
        node.is_expanded = True
        return self._predict_root_value(state, root_player=root_player, value=value)

    def _resolve_pending_batch(self, pending_batch: list[dict[str, object]], *, root_player: int) -> None:
        if not pending_batch:
            return
        leaf_requests: list[tuple[object, int]] = []
        leaf_items: list[dict[str, object]] = []
        for pending in pending_batch:
            terminal_value = pending.get("terminal_value")
            if terminal_value is not None:
                self._backup(pending["path"], float(terminal_value))
                continue
            leaf_state = pending.get("leaf_state")
            if leaf_state is None:
                continue
            leaf_items.append(pending)
            leaf_requests.append((leaf_state, int(leaf_state.current_player())))
        if not leaf_requests:
            return
        predictions = self.evaluator._predict_many(leaf_requests)
        for pending, (priors, value) in zip(leaf_items, predictions, strict=False):
            expanded_value = self._expand_from_prediction(
                pending["leaf_node"],
                pending["leaf_state"],
                root_player=root_player,
                priors=priors,
                value=float(value),
                root_noise=False,
            )
            self._backup(pending["path"], expanded_value)

    def _expand(self, node: _PerfectInfoNode, state, *, root_player: int, root_noise: bool = False) -> float:
        current_player = state.current_player()
        node.to_play = current_player
        if state.is_terminal():
            node.is_expanded = True
            node.legal_mask = np.zeros(int(state.get_game().num_distinct_actions()), dtype=np.float32)
            node.children = {}
            return _returns_to_value(list(state.returns()), root_player)
        priors = np.zeros(int(state.get_game().num_distinct_actions()), dtype=np.float32)
        for action, prob in self.evaluator.prior(state):
            priors[int(action)] = float(prob)
        legal_mask = legal_action_mask(state.get_game(), state, current_player)
        priors = _normalize_policy(priors, legal_mask)
        if root_noise:
            priors = _apply_dirichlet_noise(priors, legal_mask, alpha=self.root_noise_alpha)
        node.legal_mask = legal_mask
        node.children = {
            int(action): _PerfectInfoNode(prior=float(priors[int(action)]), to_play=1 - current_player)
            for action in np.flatnonzero(legal_mask > 0)
        }
        node.is_expanded = True
        return _returns_to_value(list(self.evaluator.evaluate(state)), root_player)

    def _select_child(self, node: _PerfectInfoNode) -> tuple[int, _PerfectInfoNode]:
        assert node.children
        total = max(node.visit_count, 1)
        return max(
            node.children.items(),
            key=lambda item: item[1].q_value
            + self.c_puct * item[1].prior * ((total**0.5) / (1 + item[1].visit_count)),
        )

    def _simulate(self, node: _PerfectInfoNode, state, *, root_player: int) -> float:
        if state.is_terminal():
            value = _returns_to_value(list(state.returns()), root_player)
            node.visit_count += 1
            node.value_sum += value
            return value
        if state.is_chance_node():
            outcomes = state.chance_outcomes()
            action = random.choices([a for a, _ in outcomes], [p for _, p in outcomes])[0]
            state.apply_action(action)
            value = self._simulate(node, state, root_player=root_player)
            return value
        if not node.is_expanded:
            value = self._expand(node, state, root_player=root_player, root_noise=False)
            node.visit_count += 1
            node.value_sum += value
            return value
        action, child = self._select_child(node)
        state.apply_action(int(action))
        value = self._simulate(child, state, root_player=root_player)
        node.visit_count += 1
        node.value_sum += value
        return value


class ImperfectInfoPuctSearch(_BaseRootSearch):
    family = "imperfect_puct"

    def __init__(self, *, evaluator: "_NeuralSearchEvaluator", simulations: int, c_puct: float = 1.25, root_noise: bool = True):
        super().__init__(evaluator=evaluator, simulations=simulations, root_noise=root_noise)
        self.c_puct = c_puct

    def policy(self, state, *, root_player: int) -> np.ndarray:
        children, mask = self._children(state)
        if not children:
            return _normalize_policy(np.zeros_like(mask, dtype=np.float32), mask)
        total_visits = 0
        for _ in range(self.simulations):
            selected = max(
                children,
                key=lambda child: child.q_value + self.c_puct * child.prior * ((total_visits + 1) ** 0.5) / (1 + child.visit_count),
            )
            next_state = state.clone()
            next_state.apply_action(int(selected.action))
            value = self._rollout(next_state, root_player=root_player, max_depth=24)
            selected.visit_count += 1
            selected.value_sum += value
            total_visits += 1
        return self._visit_policy(children, mask)


def _write_artifact(
    *,
    output_dir: str,
    checkpoint_dir: Path,
    game_name: str,
    input_dim: int,
    action_dim: int,
    hidden_dim: int,
    residual_blocks: int,
    batch_size: int,
    epochs: int,
    learning_rate: float,
    weight_decay: float,
    train_rows: int,
    device: str,
    layer_norm: bool,
    architecture: str,
    feature_shape: list[int],
    model,
    metrics: dict[str, float],
) -> PolicyModelArtifact:
    torch, _, _ = _require_torch()
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = checkpoint_dir / "model.pt"
    torch.save(model.state_dict(), checkpoint_path)
    artifact = PolicyModelArtifact(
        game=game_name,
        model_dir=str(checkpoint_dir),
        checkpoint_path=str(checkpoint_path),
        input_dim=input_dim,
        action_dim=action_dim,
        hidden_dim=hidden_dim,
        residual_blocks=residual_blocks,
        batch_size=batch_size,
        epochs=epochs,
        learning_rate=learning_rate,
        weight_decay=weight_decay,
        train_rows=train_rows,
        device=device,
        model_kind="policy_value",
        training_route="selfplay",
        layer_norm=layer_norm,
        architecture=architecture,
        feature_shape=feature_shape,
        metrics=metrics,
    )
    (checkpoint_dir / "metadata.json").write_text(
        json.dumps(artifact.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return artifact


def _resolve_temperature(step_index: int) -> float:
    if step_index < 8:
        return 1.0
    if step_index < 24:
        return 0.5
    return 0.1


def _is_perfect_info_game(game_name: str) -> bool:
    return game_name in PERFECT_INFO_GAMES


def _perfect_teacher_budget(game_name: str) -> dict[str, int]:
    return dict(PERFECT_INFO_TEACHER_BUDGETS[game_name])


def _selfplay_temperature(game_name: str, step_index: int) -> float:
    if not _is_perfect_info_game(game_name):
        return _resolve_temperature(step_index)
    if step_index < 15:
        return 1.0
    if step_index < 40:
        return 0.5
    return 0.05


def _sample_action_from_policy(policy: np.ndarray, legal_mask: np.ndarray, *, temperature: float) -> int:
    legal = np.asarray(legal_mask, dtype=np.float32)
    normalized = _normalize_policy(policy, legal)
    if temperature <= 1e-6:
        return int(normalized.argmax())
    safe = np.clip(normalized, 1e-8, 1.0)
    tempered = safe ** (1.0 / max(temperature, 1e-6))
    tempered = _normalize_policy(tempered, legal)
    return int(np.random.choice(np.arange(len(tempered)), p=tempered))


def _apply_dirichlet_noise(policy: np.ndarray, legal_mask: np.ndarray, *, alpha: float = 0.3, epsilon: float = 0.25) -> np.ndarray:
    legal_indices = np.flatnonzero(np.asarray(legal_mask) > 0)
    if len(legal_indices) <= 1:
        return policy
    noise = np.random.dirichlet([alpha] * len(legal_indices)).astype(np.float32)
    blended = np.asarray(policy, dtype=np.float32).copy()
    blended[legal_indices] = (1.0 - epsilon) * blended[legal_indices] + epsilon * noise
    return _normalize_policy(blended, legal_mask)


def _returns_to_value(returns: list[float], player_id: int) -> float:
    value = float(returns[player_id])
    if value > 1.0:
        return 1.0
    if value < -1.0:
        return -1.0
    return value


def _teacher_action(policy, state, player_id: int) -> int:
    try:
        probabilities = policy.action_probabilities(state)
    except TypeError:
        probabilities = policy.action_probabilities(state, player_id=player_id)
    legal = state.legal_actions(player_id)
    filtered = {action: float(prob) for action, prob in probabilities.items() if action in legal}
    if not filtered:
        raise RuntimeError("Teacher policy returned no legal actions")
    return max(filtered.items(), key=lambda item: item[1])[0]


def _build_empty_policy_artifact(game_name: str, output_dir: str) -> tuple[PolicyModelArtifact, object]:
    spec_game = _base_selfplay_game(game_name)
    state = spec_game.new_initial_state()
    spec = feature_spec_for_game(game_name, resolve_game_trajectory_generator(game_name).game_params)
    spec = spec.model_copy(
        update={
            "input_dim": int(extract_state_features(state, 0 if spec_game.num_players() else 0).shape[0]),
            "action_dim": int(spec_game.num_distinct_actions()),
            "feature_shape": _selfplay_feature_shape(game_name),
        }
    )
    config = default_selfplay_model_config(game_name)
    model = build_policy_model_module(
        input_dim=spec.input_dim,
        hidden_dim=int(config["hidden_dim"]),
        action_dim=spec.action_dim,
        model_kind="policy_value",
        residual_blocks=int(config["residual_blocks"]),
        layer_norm=bool(config["layer_norm"]),
        architecture=str(config.get("architecture", "mlp")),
        feature_shape=spec.feature_shape,
    )
    artifact = _write_artifact(
        output_dir=output_dir,
        checkpoint_dir=_latest_dir(output_dir),
        game_name=game_name,
        input_dim=spec.input_dim,
        action_dim=spec.action_dim,
        hidden_dim=int(config["hidden_dim"]),
        residual_blocks=int(config["residual_blocks"]),
        batch_size=0,
        epochs=0,
        learning_rate=0.0,
        weight_decay=0.0,
        train_rows=0,
        device="cpu",
        layer_norm=bool(config["layer_norm"]),
        architecture=str(config.get("architecture", "mlp")),
        feature_shape=list(spec.feature_shape),
        model=model,
        metrics={},
    )
    best_dir = _best_dir(output_dir)
    best_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_latest_dir(output_dir) / "model.pt", best_dir / "model.pt")
    shutil.copy2(_latest_dir(output_dir) / "metadata.json", best_dir / "metadata.json")
    return artifact, model




def _checkpoint_pool(output_dir: str) -> list[Path]:
    pool: list[Path] = []
    best = _best_dir(output_dir)
    if (best / "metadata.json").exists() and (best / "model.pt").exists():
        pool.append(best)
    history_candidates = sorted(_history_dir(output_dir).glob("*"), reverse=True)
    for candidate in history_candidates[:3]:
        if (candidate / "metadata.json").exists() and (candidate / "model.pt").exists():
            pool.append(candidate)
    latest = _latest_dir(output_dir)
    if not pool and (latest / "metadata.json").exists() and (latest / "model.pt").exists():
        pool.append(latest)
    return pool


def _compatible_checkpoint_pool(
    *,
    output_dir: str,
    input_dim: int,
    action_dim: int,
    architecture: str,
    feature_shape: list[int],
) -> list[Path]:
    compatible: list[Path] = []
    for candidate in _checkpoint_pool(output_dir):
        metadata_path = candidate / "metadata.json"
        if not metadata_path.exists():
            continue
        try:
            artifact = PolicyModelArtifact.model_validate_json(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if (
            artifact.training_route == "selfplay"
            and artifact.model_kind == "policy_value"
            and artifact.input_dim == input_dim
            and artifact.action_dim == action_dim
            and artifact.architecture == architecture
            and list(artifact.feature_shape or [artifact.input_dim]) == list(feature_shape)
        ):
            compatible.append(candidate)
    return compatible


def _expected_feature_shape(game_name: str) -> tuple[int, int]:
    game = _base_selfplay_game(game_name)
    state = game.new_initial_state()
    input_dim = int(extract_state_features(state, 0 if game.num_players() else 0).shape[0])
    action_dim = int(game.num_distinct_actions())
    return input_dim, action_dim


def _autotune_batch_size(
    *,
    game_name: str,
    output_dir: str,
    input_dim: int,
    action_dim: int,
    device: str,
    requested_batch_size: int,
) -> int:
    profile = _runtime_profile(game_name)
    candidates = [int(value) for value in profile.get("batch_candidates", [requested_batch_size])]
    if requested_batch_size > 0:
        candidates = [value for value in candidates if value <= requested_batch_size] or [requested_batch_size]
    path = _autotune_path(output_dir)
    if path.exists():
        try:
            payload = _load_json(path)
            if int(payload.get("input_dim", 0)) == input_dim and int(payload.get("action_dim", 0)) == action_dim:
                return int(payload.get("batch_size", candidates[0]))
        except Exception:
            pass

    torch, _, _ = _require_torch()
    resolved_device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    if not resolved_device.startswith("cuda"):
        chosen = candidates[0]
        _save_json(
            path,
            {
                "game": game_name,
                "device": resolved_device,
                "input_dim": input_dim,
                "action_dim": action_dim,
                "batch_size": chosen,
                "tested": candidates,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return chosen

    config = default_selfplay_model_config(game_name)
    feature_shape = _selfplay_feature_shape(game_name)
    chosen = candidates[0]
    for candidate in reversed(sorted(set(candidates))):
        model = build_policy_model_module(
            input_dim=input_dim,
            hidden_dim=int(config["hidden_dim"]),
            action_dim=action_dim,
            model_kind="policy_value",
            residual_blocks=int(config["residual_blocks"]),
            layer_norm=bool(config["layer_norm"]),
            architecture=str(config.get("architecture", "mlp")),
            feature_shape=feature_shape,
        ).to(resolved_device)
        try:
            if str(config.get("architecture", "mlp")) == "resnet":
                model = model.to(memory_format=torch.channels_last)
            features = torch.zeros(candidate, input_dim, device=resolved_device, dtype=torch.float32)
            masks = torch.ones(candidate, action_dim, device=resolved_device, dtype=torch.float32)
            target_policy = torch.full((candidate, action_dim), 1.0 / max(action_dim, 1), device=resolved_device)
            target_value = torch.zeros(candidate, device=resolved_device, dtype=torch.float32)
            optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type="cuda", dtype=torch.bfloat16, enabled=True):
                logits, values = model(features)
                masked_logits = logits.masked_fill(masks <= 0, -1e9)
                log_probs = torch.nn.functional.log_softmax(masked_logits, dim=1)
                probs = torch.exp(log_probs)
                policy_loss = -(target_policy * log_probs).sum(dim=1).mean()
                value_loss = torch.nn.functional.mse_loss(values, target_value)
                entropy = -(probs * log_probs).sum(dim=1).mean()
                loss = policy_loss + value_loss - 0.01 * entropy
            loss.backward()
            optimizer.step()
            chosen = candidate
            del optimizer, model, features, masks, target_policy, target_value, logits, values, loss
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            break
        except RuntimeError:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            continue
    _save_json(
        path,
        {
            "game": game_name,
            "device": resolved_device,
            "input_dim": input_dim,
            "action_dim": action_dim,
            "batch_size": chosen,
            "tested": candidates,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return chosen


def _selfplay_feature_shape(game_name: str) -> list[int]:
    game = _base_selfplay_game(game_name)
    state = game.new_initial_state()
    features = extract_state_features(state, 0 if game.num_players() else 0)
    if _is_perfect_info_game(game_name):
        return feature_spec_for_state(game_name, state, 0 if game.num_players() else 0).feature_shape
    return [int(features.shape[0])]


def _round_replay_dir(output_dir: str) -> Path:
    path = _replay_meta_path(output_dir).parent / "rounds"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _round_replay_path(output_dir: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return _round_replay_dir(output_dir) / f"round-{stamp}.npz"


def _load_replay_arrays(path: Path) -> dict[str, np.ndarray]:
    payload = np.load(path)
    return {key: payload[key] for key in payload.files}


def _compatible_round_paths(*, game_name: str, output_dir: str) -> list[Path]:
    expected_input_dim, expected_action_dim = _expected_feature_shape(game_name)
    compatible: list[Path] = []
    for path in sorted(_round_replay_dir(output_dir).glob("round-*.npz")):
        arrays = _load_replay_arrays(path)
        if int(arrays["features"].shape[1]) != expected_input_dim:
            continue
        if int(arrays["legal_masks"].shape[1]) != expected_action_dim:
            continue
        compatible.append(path)
    return compatible


def _prune_incompatible_replay_state(*, game_name: str, output_dir: str) -> None:
    expected_input_dim, expected_action_dim = _expected_feature_shape(game_name)
    for path in sorted(_round_replay_dir(output_dir).glob("round-*.npz")):
        arrays = _load_replay_arrays(path)
        if (
            int(arrays["features"].shape[1]) != expected_input_dim
            or int(arrays["legal_masks"].shape[1]) != expected_action_dim
        ):
            path.unlink(missing_ok=True)
            path.with_suffix(".json").unlink(missing_ok=True)

    replay_path = _replay_path(output_dir)
    meta_path = _replay_meta_path(output_dir)
    compatible_paths = _compatible_round_paths(game_name=game_name, output_dir=output_dir)
    if compatible_paths:
        rewrite = not replay_path.exists()
        if replay_path.exists():
            replay_arrays = _load_replay(str(replay_path))
            rewrite = (
                int(replay_arrays["features"].shape[1]) != expected_input_dim
                or int(replay_arrays["legal_masks"].shape[1]) != expected_action_dim
            )
        if rewrite:
            merged_payload = _merge_recent_replay_window(
                game_name=game_name,
                output_dir=output_dir,
                rng_seed=len(compatible_paths),
                max_rounds=REPLAY_WINDOW_ROUNDS,
                max_rows=REPLAY_WINDOW_ROWS,
                recent_fraction=RECENT_REPLAY_FRACTION,
            )
            replay_path.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(replay_path, **merged_payload)
            _save_json(
                meta_path,
                {
                    "game": game_name,
                    "episodes": 0,
                    "rows": int(merged_payload["features"].shape[0]),
                    "input_dim": int(merged_payload["features"].shape[1]),
                    "action_dim": int(merged_payload["legal_masks"].shape[1]),
                    "simulations": 0,
                    "replay_window_rounds": REPLAY_WINDOW_ROUNDS,
                    "replay_window_rows": REPLAY_WINDOW_ROWS,
                    "recent_fraction": RECENT_REPLAY_FRACTION,
                    "coverage": {},
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        return

    replay_path.unlink(missing_ok=True)
    meta_path.unlink(missing_ok=True)


def _sample_rows(
    arrays: dict[str, np.ndarray],
    *,
    take: int,
    rng: np.random.Generator,
) -> dict[str, np.ndarray]:
    total = int(arrays["features"].shape[0])
    if take >= total:
        return arrays
    indices = np.sort(rng.choice(total, size=take, replace=False))
    return {key: value[indices] for key, value in arrays.items()}


def _concat_replays(chunks: list[dict[str, np.ndarray]]) -> dict[str, np.ndarray]:
    if not chunks:
        raise ValueError("No replay chunks to concatenate")
    keys = list(chunks[0].keys())
    return {key: np.concatenate([chunk[key] for chunk in chunks], axis=0) for key in keys}


def _payload_coverage(payload: dict[str, np.ndarray]) -> dict[str, object]:
    legal_masks = payload["legal_masks"]
    policy_targets = payload["policy_targets"]
    game_steps = payload["game_steps"]
    state_keys = payload["state_keys"]
    unique_state_keys = len(set(state_keys.tolist()))
    supported_actions = set()
    entropies = []
    depth_hist: dict[str, int] = {}
    for mask, target, step in zip(legal_masks, policy_targets, game_steps, strict=False):
        for action in np.flatnonzero(mask > 0):
            supported_actions.add(int(action))
        safe = np.clip(target, 1e-8, 1.0)
        entropies.append(float(-(safe * np.log(safe)).sum()))
        bucket = str(min(int(step) // 5 * 5, 95))
        depth_hist[bucket] = depth_hist.get(bucket, 0) + 1
    duplicate_ratio = 1.0 - (unique_state_keys / max(int(state_keys.shape[0]), 1))
    return {
        "unique_state_keys": unique_state_keys,
        "unique_action_support": len(supported_actions),
        "duplicate_ratio": duplicate_ratio,
        "mean_policy_entropy": float(sum(entropies) / max(len(entropies), 1)),
        "step_depth_histogram": depth_hist,
    }


def _persist_round_replay(
    *,
    output_dir: str,
    game_name: str,
    payload: dict[str, np.ndarray],
    simulations: int,
    coverage: dict[str, object],
) -> Path:
    round_path = _round_replay_path(output_dir)
    np.savez_compressed(round_path, **payload)
    meta_path = round_path.with_suffix(".json")
    _save_json(
        meta_path,
        {
            "game": game_name,
            "path": str(round_path),
            "rows": int(payload["features"].shape[0]),
            "simulations": simulations,
            "coverage": coverage,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return round_path


def _merge_recent_replay_window(
    *,
    game_name: str,
    output_dir: str,
    rng_seed: int,
    max_rounds: int = REPLAY_WINDOW_ROUNDS,
    max_rows: int = REPLAY_WINDOW_ROWS,
    recent_fraction: float = RECENT_REPLAY_FRACTION,
) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(rng_seed)
    round_paths = _compatible_round_paths(game_name=game_name, output_dir=output_dir)
    if not round_paths:
        raise RuntimeError("No self-play rounds available to merge")
    selected_paths = round_paths[-max_rounds:]
    recent_path = selected_paths[-1]
    history_paths = selected_paths[:-1]
    recent_arrays = _load_replay_arrays(recent_path)
    history_arrays = [_load_replay_arrays(path) for path in history_paths]

    recent_cap = int(max_rows * recent_fraction)
    history_cap = max_rows - recent_cap
    sampled_chunks: list[dict[str, np.ndarray]] = []

    recent_take = min(int(recent_arrays["features"].shape[0]), max(recent_cap, 1))
    sampled_chunks.append(_sample_rows(recent_arrays, take=recent_take, rng=rng))

    if history_arrays and history_cap > 0:
        merged_history = _concat_replays(history_arrays)
        history_take = min(int(merged_history["features"].shape[0]), history_cap)
        if history_take > 0:
            sampled_chunks.append(_sample_rows(merged_history, take=history_take, rng=rng))

    merged = _concat_replays(sampled_chunks)
    indices = np.arange(int(merged["features"].shape[0]))
    rng.shuffle(indices)
    return {key: value[indices] for key, value in merged.items()}


def _base_selfplay_game(game_name: str):
    pyspiel = _require_search()
    spec = resolve_game_trajectory_generator(game_name)
    base_game = pyspiel.load_game(game_name, spec.game_params)
    if game_name == "goofspiel":
        return pyspiel.convert_to_turn_based(base_game)
    return base_game


def _build_replay_chunk(
    *,
    game_name: str,
    checkpoint_dirs: list[str],
    shared_predictors: dict[str, _SharedBatchedPredictor] | None = None,
    use_process_predictors: bool = False,
    episode_start: int,
    episode_count: int,
    start_seed: int,
    simulations: int,
) -> dict[str, np.ndarray]:
    game = _base_selfplay_game(game_name)
    input_dim, action_dim = _expected_feature_shape(game_name)
    pool = list(checkpoint_dirs)
    if not pool:
        raise RuntimeError(f"No compatible self-play checkpoints available for {game_name}")

    loaded_models: dict[str, tuple[PolicyModelArtifact, object]] = {}
    rows: list[_ReplayRow] = []
    rng = random.Random(start_seed + episode_start * 7919)

    for local_idx in range(max(int(episode_count), 1)):
        episode_id = episode_start + local_idx
        checkpoint_dir = rng.choice(pool)
        if use_process_predictors:
            evaluator = _ProcessSharedSearchEvaluator(
                predictor=_process_predictor_client(checkpoint_dir),
                action_dim=action_dim,
            )
        elif shared_predictors is not None:
            predictor = shared_predictors[checkpoint_dir]
            evaluator = _SharedSearchEvaluator(
                artifact=predictor.artifact,
                predictor=predictor,
                action_dim=action_dim,
            )
        else:
            if checkpoint_dir not in loaded_models:
                artifact, model = _load_checkpoint_dir(Path(checkpoint_dir))
                loaded_models[checkpoint_dir] = (artifact, _materialize_replay_model(game_name, artifact, model))
            artifact, model = loaded_models[checkpoint_dir]
            evaluator = _NeuralSearchEvaluator(artifact=artifact, model=model, action_dim=action_dim)
        if _is_perfect_info_game(game_name):
            micro_batch_size = int(_runtime_profile(game_name).get("replay_micro_batch_size", 16))
            search = PerfectInfoPuctSearch(
                evaluator=evaluator,
                simulations=simulations,
                c_puct=1.5,
                root_noise_alpha=0.30 if game_name == "othello" else 0.15 if game_name == "hex" else 0.25,
                eval_batch_size=micro_batch_size,
            )
        elif game_name == "goofspiel":
            search = PuctSearch(evaluator=evaluator, simulations=simulations, c_puct=1.5, root_noise=True)
        else:
            search = ImperfectInfoPuctSearch(evaluator=evaluator, simulations=simulations, c_puct=1.25, root_noise=True)

        state = game.new_initial_state()
        episode_rows: list[_ReplayRow] = []
        step_index = 0
        while not state.is_terminal() and step_index < 512:
            if state.is_chance_node():
                outcomes = state.chance_outcomes()
                state.apply_action(rng.choices([a for a, _ in outcomes], [p for _, p in outcomes])[0])
                continue

            player_id = state.current_player()
            if player_id < 0:
                raise RuntimeError(f"{game_name} self-play expected sequential nodes, got player_id={player_id}")
            mask = legal_action_mask(game, state, player_id)
            policy_target = search.policy(state, root_player=player_id)
            features = extract_state_features(state, player_id)
            action = _sample_action_from_policy(policy_target, mask, temperature=_selfplay_temperature(game_name, step_index))
            episode_rows.append(
                _ReplayRow(
                    features=features,
                    legal_mask=mask,
                    policy_target=policy_target,
                    value_target=0.0,
                    player_id=player_id,
                    game_step=step_index,
                    episode_id=episode_id,
                    state_key=_state_key(state, player_id),
                )
            )
            state.apply_action(action)
            step_index += 1

        if not state.is_terminal() or not episode_rows:
            continue

        returns = list(state.returns())
        for row in episode_rows:
            row.value_target = _returns_to_value(returns, row.player_id)
            rows.append(row)

    if not rows:
        return {}
    state_key_width = max(len(row.state_key) for row in rows)
    return {
        "features": np.stack([row.features for row in rows]).astype(np.float32),
        "legal_masks": np.stack([row.legal_mask for row in rows]).astype(np.float32),
        "policy_targets": np.stack([row.policy_target for row in rows]).astype(np.float32),
        "value_targets": np.asarray([row.value_target for row in rows], dtype=np.float32),
        "player_ids": np.asarray([row.player_id for row in rows], dtype=np.int64),
        "game_steps": np.asarray([row.game_step for row in rows], dtype=np.int64),
        "episode_ids": np.asarray([row.episode_id for row in rows], dtype=np.int64),
        "state_keys": np.asarray([row.state_key for row in rows], dtype=f"<U{state_key_width}"),
    }


def build_selfplay_replay(
    *,
    game_name: str,
    output_dir: str,
    episodes: int,
    start_seed: int,
    simulations: int,
    replay_window_rounds: int | None = None,
    replay_window_rows: int | None = None,
    recent_fraction: float | None = None,
    progress_callback=None,
) -> ReplayBufferReport:
    _require_search()
    _ensure_dirs(output_dir)
    profile = _runtime_profile(game_name)
    replay_window_rounds = int(replay_window_rounds or profile.get("replay_window_rounds", REPLAY_WINDOW_ROUNDS))
    replay_window_rows = int(replay_window_rows or profile.get("replay_window_rows", REPLAY_WINDOW_ROWS))
    recent_fraction = float(recent_fraction or profile.get("recent_fraction", RECENT_REPLAY_FRACTION))
    game = _base_selfplay_game(game_name)
    input_dim, action_dim = _expected_feature_shape(game_name)
    architecture = str(default_selfplay_model_config(game_name).get("architecture", "mlp"))
    feature_shape = _selfplay_feature_shape(game_name)
    pool = _compatible_checkpoint_pool(
        output_dir=output_dir,
        input_dim=input_dim,
        action_dim=action_dim,
        architecture=architecture,
        feature_shape=feature_shape,
    )
    if not pool:
        _build_empty_policy_artifact(game_name, output_dir)
        pool = _compatible_checkpoint_pool(
            output_dir=output_dir,
            input_dim=input_dim,
            action_dim=action_dim,
            architecture=architecture,
            feature_shape=feature_shape,
        )
    actor_workers = max(1, int(profile.get("actor_workers", 1)))
    checkpoint_dirs = [str(path) for path in pool]
    chunk_payloads: list[dict[str, np.ndarray]] = []
    rows_so_far = 0
    completed_episodes = 0
    total_episodes = max(int(episodes), 1)
    chunk_size = 1 if actor_workers <= 1 else max(1, min(16, (total_episodes + actor_workers - 1) // actor_workers))
    tasks = []
    episode_cursor = 0
    while episode_cursor < total_episodes:
        take = min(chunk_size, total_episodes - episode_cursor)
        tasks.append((episode_cursor, take))
        episode_cursor += take

    torch, _, _ = _require_torch()
    use_shared_gpu_predictor = bool(torch.cuda.is_available())

    if use_shared_gpu_predictor and actor_workers > 1 and len(tasks) > 1:
        max_workers = min(actor_workers, len(tasks))
        if _is_perfect_info_game(game_name):
            max_workers = min(max_workers, int(profile.get("gpu_actor_concurrency", 8)))
        mp_context = mp.get_context("spawn")
        shared_queues, shared_servers = _build_process_predictor_pool(
            game_name=game_name,
            checkpoint_dirs=checkpoint_dirs,
            action_dim=action_dim,
            mp_context=mp_context,
        )
        try:
            with ProcessPoolExecutor(
                max_workers=max_workers,
                mp_context=mp_context,
                initializer=_init_process_predictor_clients,
                initargs=(shared_queues,),
            ) as executor:
                future_map = {
                    executor.submit(
                        _build_replay_chunk,
                        game_name=game_name,
                        checkpoint_dirs=checkpoint_dirs,
                        use_process_predictors=True,
                        episode_start=episode_start,
                        episode_count=episode_count,
                        start_seed=start_seed,
                        simulations=simulations,
                    ): episode_count
                    for episode_start, episode_count in tasks
                }
                for future in as_completed(future_map):
                    episode_count = future_map[future]
                    payload = future.result()
                    completed_episodes += episode_count
                    if payload:
                        chunk_payloads.append(payload)
                        rows_so_far += int(payload["features"].shape[0])
                    if progress_callback is not None:
                        progress_callback(completed_episodes, rows_so_far)
        finally:
            for server in shared_servers.values():
                server.close()
    elif actor_workers > 1 and len(tasks) > 1:
        max_workers = min(actor_workers, len(tasks))
        if _is_perfect_info_game(game_name):
            max_workers = min(max_workers, int(profile.get("gpu_actor_concurrency", 8)))
        executor_kwargs: dict[str, object] = {"max_workers": max_workers}
        if _is_perfect_info_game(game_name):
            executor_kwargs["mp_context"] = mp.get_context("spawn")
        with ProcessPoolExecutor(**executor_kwargs) as executor:
            future_map = {
                executor.submit(
                    _build_replay_chunk,
                    game_name=game_name,
                    checkpoint_dirs=checkpoint_dirs,
                    episode_start=episode_start,
                    episode_count=episode_count,
                    start_seed=start_seed,
                    simulations=simulations,
                ): episode_count
                for episode_start, episode_count in tasks
            }
            for future in as_completed(future_map):
                episode_count = future_map[future]
                payload = future.result()
                completed_episodes += episode_count
                if payload:
                    chunk_payloads.append(payload)
                    rows_so_far += int(payload["features"].shape[0])
                if progress_callback is not None:
                    progress_callback(completed_episodes, rows_so_far)
    elif use_shared_gpu_predictor:
        shared_predictors = _build_shared_predictor_pool(
            game_name=game_name,
            checkpoint_dirs=checkpoint_dirs,
            action_dim=action_dim,
        )
        try:
            for episode_start, episode_count in tasks:
                payload = _build_replay_chunk(
                    game_name=game_name,
                    checkpoint_dirs=checkpoint_dirs,
                    shared_predictors=shared_predictors,
                    episode_start=episode_start,
                    episode_count=episode_count,
                    start_seed=start_seed,
                    simulations=simulations,
                )
                completed_episodes += episode_count
                if payload:
                    chunk_payloads.append(payload)
                    rows_so_far += int(payload["features"].shape[0])
                if progress_callback is not None:
                    progress_callback(completed_episodes, rows_so_far)
        finally:
            for predictor in shared_predictors.values():
                predictor.close()
    else:
        for episode_start, episode_count in tasks:
            payload = _build_replay_chunk(
                game_name=game_name,
                checkpoint_dirs=checkpoint_dirs,
                episode_start=episode_start,
                episode_count=episode_count,
                start_seed=start_seed,
                simulations=simulations,
            )
            completed_episodes += episode_count
            if payload:
                chunk_payloads.append(payload)
                rows_so_far += int(payload["features"].shape[0])
            if progress_callback is not None:
                progress_callback(completed_episodes, rows_so_far)

    if not chunk_payloads:
        raise RuntimeError(f"GAME self-play replay generation produced no rows for {game_name}")
    current_payload = _concat_replays(chunk_payloads)
    coverage = _payload_coverage(current_payload)
    _persist_round_replay(
        output_dir=output_dir,
        game_name=game_name,
        payload=current_payload,
        simulations=simulations,
        coverage=coverage,
    )
    merged_payload = _merge_recent_replay_window(
        game_name=game_name,
        output_dir=output_dir,
        rng_seed=start_seed + episodes + simulations,
        max_rounds=replay_window_rounds,
        max_rows=replay_window_rows,
        recent_fraction=recent_fraction,
    )
    replay_path = _replay_path(output_dir)
    replay_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(replay_path, **merged_payload)
    _save_json(
        _replay_meta_path(output_dir),
        {
            "game": game_name,
            "episodes": episodes,
            "rows": int(merged_payload["features"].shape[0]),
            "input_dim": int(merged_payload["features"].shape[1]),
            "action_dim": int(merged_payload["legal_masks"].shape[1]),
            "simulations": simulations,
            "replay_window_rounds": replay_window_rounds,
            "replay_window_rows": replay_window_rows,
            "recent_fraction": recent_fraction,
            "coverage": coverage,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return ReplayBufferReport(
        game=game_name,
        output=str(replay_path),
        episodes=episodes,
        rows=int(merged_payload["features"].shape[0]),
        input_dim=int(merged_payload["features"].shape[1]),
        action_dim=int(merged_payload["legal_masks"].shape[1]),
        simulations=simulations,
        generator_family="perfect_puct" if _is_perfect_info_game(game_name) else "puct" if game_name == "goofspiel" else "imperfect_puct",
        unique_state_keys=int(coverage["unique_state_keys"]),
        unique_action_support=int(coverage["unique_action_support"]),
        duplicate_ratio=float(coverage["duplicate_ratio"]),
        mean_policy_entropy=float(coverage["mean_policy_entropy"]),
        step_depth_histogram=dict(coverage["step_depth_histogram"]),
    )


def _load_replay(path: str) -> dict[str, np.ndarray]:
    payload = np.load(path)
    return {key: payload[key] for key in payload.files}


def _train_from_replay(
    *,
    game_name: str,
    replay_path: str,
    output_dir: str,
    epochs: int,
    batch_size: int,
    learning_rate: float,
    weight_decay: float,
    device: str,
) -> PolicyModelArtifact:
    torch, DataLoader, TensorDataset = _require_torch()
    payload = _load_replay(replay_path)
    features = payload["features"].astype(np.float32)
    legal_masks = payload["legal_masks"].astype(np.float32)
    policy_targets = payload["policy_targets"].astype(np.float32)
    value_targets = payload["value_targets"].astype(np.float32)
    if len(features) == 0:
        raise ValueError("Self-play replay buffer is empty")

    config = default_selfplay_model_config(game_name)
    runtime_profile = _runtime_profile(game_name)
    resolved_device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    layer_norm = bool(config["layer_norm"])
    residual_blocks = int(config["residual_blocks"])
    hidden_dim = int(config["hidden_dim"])
    architecture = str(config.get("architecture", "mlp"))
    feature_shape = _selfplay_feature_shape(game_name)

    latest_dir = _latest_dir(output_dir)
    should_reinit = True
    if (latest_dir / "metadata.json").exists() and (latest_dir / "model.pt").exists():
        loaded_artifact, loaded_model = load_policy_model(str(latest_dir))
        if (
            loaded_artifact.training_route == "selfplay"
            and loaded_artifact.model_kind == "policy_value"
            and loaded_artifact.input_dim == int(features.shape[1])
            and loaded_artifact.action_dim == int(legal_masks.shape[1])
            and loaded_artifact.architecture == architecture
            and list(loaded_artifact.feature_shape or [loaded_artifact.input_dim]) == feature_shape
        ):
            model = loaded_model.to(resolved_device)
            artifact = loaded_artifact
            should_reinit = False
        else:
            artifact = None
    else:
        model = build_policy_model_module(
            input_dim=int(features.shape[1]),
            hidden_dim=hidden_dim,
            action_dim=int(legal_masks.shape[1]),
            model_kind="policy_value",
            residual_blocks=residual_blocks,
            layer_norm=layer_norm,
            architecture=architecture,
            feature_shape=feature_shape,
        ).to(resolved_device)
        artifact = None
        should_reinit = False
    if should_reinit:
        model = build_policy_model_module(
            input_dim=int(features.shape[1]),
            hidden_dim=hidden_dim,
            action_dim=int(legal_masks.shape[1]),
            model_kind="policy_value",
            residual_blocks=residual_blocks,
            layer_norm=layer_norm,
            architecture=architecture,
            feature_shape=feature_shape,
        ).to(resolved_device)

    if hasattr(torch, "set_float32_matmul_precision"):
        torch.set_float32_matmul_precision("high")
    if resolved_device.startswith("cuda") and architecture == "resnet":
        model = model.to(memory_format=torch.channels_last)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=weight_decay)
    dataset = TensorDataset(
        torch.from_numpy(features),
        torch.from_numpy(legal_masks),
        torch.from_numpy(policy_targets),
        torch.from_numpy(value_targets),
    )
    effective_batch_size = min(batch_size, len(dataset))
    worker_count = int(runtime_profile.get("dataloader_workers", 4 if not _is_perfect_info_game(game_name) else 8))
    if len(dataset) < 512:
        worker_count = 0
    loader = DataLoader(
        dataset,
        batch_size=effective_batch_size,
        shuffle=True,
        num_workers=worker_count,
        pin_memory=resolved_device.startswith("cuda"),
        persistent_workers=worker_count > 0,
    )
    scaler_enabled = resolved_device.startswith("cuda")
    autocast_dtype = torch.bfloat16 if scaler_enabled else None
    final_policy_loss = 0.0
    final_value_loss = 0.0
    final_entropy = 0.0
    for _ in range(max(int(epochs), 1)):
        total_policy = 0.0
        total_value = 0.0
        total_entropy = 0.0
        total_seen = 0
        model.train()
        for batch_features, batch_masks, batch_policy, batch_value in loader:
            batch_features = batch_features.to(resolved_device)
            batch_masks = batch_masks.to(resolved_device)
            batch_policy = batch_policy.to(resolved_device)
            batch_value = batch_value.to(resolved_device)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type="cuda", dtype=autocast_dtype, enabled=scaler_enabled):
                logits, values = model(batch_features)
                masked_logits = logits.masked_fill(batch_masks <= 0, -1e9)
                log_probs = torch.nn.functional.log_softmax(masked_logits, dim=1)
                probs = torch.exp(log_probs)
                policy_loss = -(batch_policy * log_probs).sum(dim=1).mean()
                value_loss = torch.nn.functional.mse_loss(values, batch_value)
                entropy = -(probs * log_probs).sum(dim=1).mean()
                loss = policy_loss + value_loss - 0.01 * entropy
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            batch_seen = int(batch_features.shape[0])
            total_policy += float(policy_loss.detach().cpu()) * batch_seen
            total_value += float(value_loss.detach().cpu()) * batch_seen
            total_entropy += float(entropy.detach().cpu()) * batch_seen
            total_seen += batch_seen
        if total_seen:
            final_policy_loss = total_policy / total_seen
            final_value_loss = total_value / total_seen
            final_entropy = total_entropy / total_seen

    checkpoint_dir = _latest_dir(output_dir)
    artifact = _write_artifact(
        output_dir=output_dir,
        checkpoint_dir=checkpoint_dir,
        game_name=game_name,
        input_dim=int(features.shape[1]),
        action_dim=int(legal_masks.shape[1]),
        hidden_dim=hidden_dim,
        residual_blocks=residual_blocks,
        batch_size=batch_size,
        epochs=max(int(epochs), 1),
        learning_rate=learning_rate,
        weight_decay=weight_decay,
        train_rows=int(features.shape[0]),
        device=resolved_device,
        layer_norm=layer_norm,
        architecture=architecture,
        feature_shape=feature_shape,
        model=model,
        metrics={
            "policy_loss": final_policy_loss,
            "value_loss": final_value_loss,
            "entropy": final_entropy,
        },
    )
    if artifact:
        return artifact
    raise RuntimeError("Self-play training failed to produce a checkpoint")


def _resolve_policy_model_checkpoint(model_dir: str) -> Path:
    root = Path(model_dir)
    for candidate in (root / "best", root, root / "latest"):
        if (candidate / "metadata.json").exists() and (candidate / "model.pt").exists():
            return candidate
    raise FileNotFoundError(f"Missing policy-model artifact in {root}")


def _model_action(model_artifact: PolicyModelArtifact, model, state, player_id: int) -> int:
    import torch

    features = extract_state_features(state, player_id)
    mask = legal_action_mask(state.get_game(), state, player_id)
    device = next(model.parameters()).device
    with torch.no_grad():
        feature_tensor = torch.from_numpy(features).float().to(device).unsqueeze(0)
        mask_tensor = torch.from_numpy(mask).float().to(device).unsqueeze(0)
        output = model(feature_tensor)
        logits = extract_policy_logits(output)
        masked_logits = logits.masked_fill(mask_tensor <= 0, -1e9)
        action = int(masked_logits.argmax(dim=1).item())
    if mask[action] <= 0:
        raise RuntimeError("Policy model selected an illegal action")
    return action


def _teacher_context(game_name: str) -> tuple[LoadedPolicySnapshot, object]:
    if _is_perfect_info_game(game_name):
        raise ValueError(f"{game_name} uses MCTS teacher baseline, not a policy snapshot")
    spec = resolve_game_trajectory_generator(game_name)
    if spec.family not in {"cfr", "mccfr", "deep_cfr"}:
        raise ValueError(f"{game_name} does not expose a teacher snapshot family")
    target = Path(spec.policy_path)
    if not target.exists():
        build_policy_snapshot(
            game_name=game_name,
            generator_name=spec.name,
            family=spec.family,
            params=spec.game_params,
            output_path=str(target),
            iterations=spec.default_iterations,
        )
    return load_policy_snapshot(str(target))


def _perfect_teacher_action(game_name: str, state, *, seed: int) -> int:
    budget = _perfect_teacher_budget(game_name)
    bot = _game_runtime()["make_mcts_bot"](state.get_game(), budget["sim"], budget["roll"], seed=seed % (2**31))
    return int(bot.step(state))


def _arena_game(
    *,
    game_name: str,
    model_artifact: PolicyModelArtifact,
    model,
    opponent: str,
    opponent_checkpoint: str = "",
) -> ArenaEvalReport:
    raise RuntimeError("Use evaluate_selfplay_policy_model with a positive game count")


def evaluate_selfplay_policy_model(
    *,
    game_name: str,
    output_dir: str,
    opponent: str,
    games: int = 200,
    checkpoint: str = "",
    early_stop_min_win_rate: float | None = None,
) -> ArenaEvalReport:
    model_checkpoint = Path(checkpoint) if checkpoint else _resolve_policy_model_checkpoint(output_dir)
    if model_checkpoint.is_file():
        model_checkpoint = model_checkpoint.parent
    artifact, model = load_policy_model(str(model_checkpoint))
    torch, _, _ = _require_torch()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)

    base_game = _base_selfplay_game(game_name)
    teacher_snapshot = None
    teacher_policy = None
    opponent_artifact = None
    opponent_model = None
    opponent_checkpoint_path = ""
    if opponent in {"teacher", "teacher_cheap"}:
        if _is_perfect_info_game(game_name):
            budget = _perfect_teacher_budget(game_name)
            opponent_checkpoint_path = f"mcts:{budget['sim']}sim/{budget['roll']}roll"
        else:
            teacher_snapshot, teacher_policy = _teacher_context(game_name)
            opponent_checkpoint_path = teacher_snapshot.policy_path
    elif opponent == "best":
        best_checkpoint = _best_dir(output_dir)
        opponent_artifact, opponent_model = load_policy_model(str(best_checkpoint))
        opponent_model = opponent_model.to(device)
        opponent_checkpoint_path = str(best_checkpoint / "model.pt")
    elif opponent == "checkpoint":
        if not checkpoint:
            raise ValueError("checkpoint opponent requires --checkpoint")
        checkpoint_dir = Path(checkpoint)
        if checkpoint_dir.is_file():
            checkpoint_dir = checkpoint_dir.parent
        opponent_artifact, opponent_model = load_policy_model(str(checkpoint_dir))
        opponent_model = opponent_model.to(device)
        opponent_checkpoint_path = str(checkpoint_dir / "model.pt")
    else:
        raise ValueError(f"Unsupported opponent: {opponent}")

    rng = random.Random(9871)
    wins = 0
    losses = 0
    draws = 0
    target_games = max(int(games), 1)
    required_wins = _required_wins_for_threshold(target_games, early_stop_min_win_rate) if early_stop_min_win_rate is not None else None
    for game_idx in range(target_games):
        state = base_game.new_initial_state()
        model_player = game_idx % base_game.num_players()
        move_count = 0
        while not state.is_terminal() and move_count < 512:
            if state.is_chance_node():
                outcomes = state.chance_outcomes()
                state.apply_action(rng.choices([a for a, _ in outcomes], [p for _, p in outcomes])[0])
                continue
            player_id = state.current_player()
            if player_id == model_player:
                action = _model_action(model_artifact=artifact, model=model, state=state, player_id=player_id)
            else:
                if opponent in {"teacher", "teacher_cheap"}:
                    if _is_perfect_info_game(game_name):
                        action = _perfect_teacher_action(game_name, state, seed=9871 + game_idx * 997 + move_count)
                    else:
                        action = _teacher_action(teacher_policy, state, player_id)
                else:
                    action = _model_action(
                        model_artifact=opponent_artifact,
                        model=opponent_model,
                        state=state,
                        player_id=player_id,
                    )
            state.apply_action(action)
            move_count += 1

        if not state.is_terminal():
            continue
        value = _returns_to_value(list(state.returns()), model_player)
        if value > 0:
            wins += 1
        elif value < 0:
            losses += 1
        else:
            draws += 1
        if required_wins is not None:
            played = wins + losses + draws
            remaining = target_games - played
            if wins >= required_wins:
                break
            if wins + remaining < required_wins:
                break

    report = _make_arena_report(
        game_name=game_name,
        opponent=opponent,
        output_dir=output_dir,
        games=wins + losses + draws,
        wins=wins,
        losses=losses,
        draws=draws,
        win_rate=(wins / max(wins + losses + draws, 1)),
        checkpoint_path=str(model_checkpoint / "model.pt"),
        opponent_checkpoint=opponent_checkpoint_path,
    )
    _save_json(_arena_path(output_dir, f"{opponent}_eval"), report.model_dump(mode="json"))
    return report


def train_selfplay_policy_model(
    *,
    game_name: str,
    output_dir: str,
    selfplay_episodes: int = 128,
    start_seed: int = 100000,
    simulations: int = 64,
    epochs: int = 5,
    batch_size: int = 1024,
    learning_rate: float = 3e-4,
    weight_decay: float = 1e-4,
    device: str = "",
    quick_gate_games: int = 50,
    quick_gate_min_win_rate: float | None = None,
    teacher_gate_games: int = 200,
    teacher_gate_min_win_rate: float | None = None,
    teacher_gate_required_streak: int | None = None,
    quick_gate_interval_updates: int | None = None,
    teacher_gate_interval_updates: int | None = None,
    sync_interval_updates: int | None = None,
    autotune_batch_size: bool = False,
    resume: bool = True,
    repo_id: str = "",
) -> SelfPlayTrainReport:
    _ensure_dirs(output_dir)
    if resume:
        restore_selfplay_artifacts_from_hf(game_name=game_name, output_dir=output_dir, repo_id=repo_id)
    _prune_incompatible_replay_state(game_name=game_name, output_dir=output_dir)
    profile = _runtime_profile(game_name)
    if quick_gate_min_win_rate is None:
        quick_gate_min_win_rate = 0.55 if _is_perfect_info_game(game_name) else 0.52
    if teacher_gate_min_win_rate is None:
        teacher_gate_min_win_rate = 0.90 if _is_perfect_info_game(game_name) else 0.60
    if teacher_gate_required_streak is None:
        teacher_gate_required_streak = 2
    if quick_gate_interval_updates is None:
        quick_gate_interval_updates = 1
    if teacher_gate_interval_updates is None:
        teacher_gate_interval_updates = 1
    if sync_interval_updates is None:
        sync_interval_updates = 1
    status = _load_status(output_dir, game_name)
    phase = _phase_name(status=status, teacher_gate_min_win_rate=teacher_gate_min_win_rate)
    phase_simulations = _phase_simulations(
        base_simulations=simulations,
        profile=profile,
        phase=phase,
    )
    learner_steps_per_phase = max(1, int(profile.get("learner_steps_per_phase", 1)))
    cheap_teacher_games = min(int(profile.get("cheap_teacher_gate_games", min(teacher_gate_games, 50))), int(teacher_gate_games))
    cheap_teacher_min_win_rate = _cheap_teacher_threshold(
        teacher_gate_min_win_rate=teacher_gate_min_win_rate,
        profile=profile,
    )
    input_dim, action_dim = _expected_feature_shape(game_name)
    effective_batch_size = (
        _autotune_batch_size(
            game_name=game_name,
            output_dir=output_dir,
            input_dim=input_dim,
            action_dim=action_dim,
            device=device,
            requested_batch_size=batch_size,
        )
        if autotune_batch_size
        else batch_size
    )
    heartbeat = SelfPlayHeartbeat(
        game=game_name,
        output_dir=output_dir,
        status="running",
        phase="replay",
        learner_updates=status.learner_updates,
        learner_steps_completed=status.learner_steps_completed,
        rows_generated_total=status.replay_rows,
        rows_consumed_total=status.replay_rows,
        replay_states_per_sec=0.0,
        last_quick_win_rate=status.last_quick_win_rate,
        last_teacher_win_rate=status.last_teacher_win_rate,
        eval_batch_size=_shared_predictor_batch_size(game_name),
        checkpoint_version=status.evaluator_version,
        last_checkpoint_at=status.last_checkpoint_at,
        last_replay_flush_at=status.last_replay_flush_at,
        autotuned_batch_size=effective_batch_size if autotune_batch_size else 0,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    gpu_util, gpu_mem = _gpu_snapshot()
    heartbeat = heartbeat.model_copy(update={"gpu_util_avg_5m": gpu_util, "gpu_mem_avg_5m": gpu_mem})
    _save_heartbeat(heartbeat)

    replay_started_at = time.perf_counter()

    def _progress_callback(completed_episodes: int, rows_so_far: int) -> None:
        nonlocal heartbeat
        gpu_util_local, gpu_mem_local = _gpu_snapshot()
        elapsed = max(time.perf_counter() - replay_started_at, 1e-6)
        heartbeat = heartbeat.model_copy(
            update={
                "rows_generated_total": status.replay_rows + rows_so_far,
                "rows_generated_last_10m": rows_so_far,
                "replay_states_per_sec": rows_so_far / elapsed,
                "gpu_util_avg_5m": gpu_util_local,
                "gpu_mem_avg_5m": gpu_mem_local,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        _save_heartbeat(heartbeat)

    replay = build_selfplay_replay(
        game_name=game_name,
        output_dir=output_dir,
        episodes=selfplay_episodes,
        start_seed=start_seed + status.train_epochs,
        simulations=phase_simulations,
        replay_window_rounds=int(profile.get("replay_window_rounds", REPLAY_WINDOW_ROUNDS)),
        replay_window_rows=int(profile.get("replay_window_rows", REPLAY_WINDOW_ROWS)),
        recent_fraction=float(profile.get("recent_fraction", RECENT_REPLAY_FRACTION)),
        progress_callback=_progress_callback,
    )
    heartbeat = heartbeat.model_copy(
        update={
            "rows_generated_total": status.replay_rows + replay.rows,
            "rows_generated_last_10m": replay.rows,
            "phase": "learn",
            "last_replay_flush_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    _save_heartbeat(heartbeat)
    artifact = _train_from_replay(
        game_name=game_name,
        replay_path=replay.output,
        output_dir=output_dir,
        epochs=max(int(epochs), 1) * learner_steps_per_phase,
        batch_size=effective_batch_size,
        learning_rate=learning_rate,
        weight_decay=weight_decay,
        device=device,
    )
    learner_updates = status.learner_updates + 1
    promoted = False
    should_run_quick = learner_updates % max(int(quick_gate_interval_updates), 1) == 0
    best_exists = (_best_dir(output_dir) / "metadata.json").exists()
    if best_exists and should_run_quick:
        heartbeat = heartbeat.model_copy(update={"phase": "quick_eval", "updated_at": datetime.now(timezone.utc).isoformat()})
        _save_heartbeat(heartbeat)
        quick_eval = evaluate_selfplay_policy_model(
            game_name=game_name,
            output_dir=output_dir,
            opponent="best",
            games=quick_gate_games,
            checkpoint=str(_latest_dir(output_dir)),
        )
    else:
        quick_eval = _make_arena_report(
            game_name=game_name,
            opponent="best",
            output_dir=output_dir,
            games=0 if best_exists else 0,
            wins=0,
            losses=0,
            draws=0,
            win_rate=status.last_quick_win_rate if best_exists and not should_run_quick else 1.0,
            passed=(status.last_quick_win_rate >= quick_gate_min_win_rate) if best_exists and not should_run_quick else True,
            checkpoint_path=str(_latest_dir(output_dir) / "model.pt"),
            opponent_checkpoint="",
        )
        _save_json(_arena_path(output_dir, "quick_eval"), quick_eval.model_dump(mode="json"))

    quick_pass = quick_eval.win_rate >= quick_gate_min_win_rate
    should_run_teacher = quick_pass and learner_updates % max(int(teacher_gate_interval_updates), 1) == 0
    cheap_teacher_eval = _make_arena_report(
        game_name=game_name,
        opponent="teacher_cheap",
        output_dir=output_dir,
        games=0,
        win_rate=status.last_cheap_teacher_win_rate,
        checkpoint_path=str(_latest_dir(output_dir) / "model.pt"),
        opponent_checkpoint="",
    )
    if should_run_teacher:
        heartbeat = heartbeat.model_copy(update={"phase": "teacher_eval", "updated_at": datetime.now(timezone.utc).isoformat()})
        _save_heartbeat(heartbeat)
        cheap_teacher_eval = evaluate_selfplay_policy_model(
            game_name=game_name,
            output_dir=output_dir,
            opponent="teacher_cheap",
            games=cheap_teacher_games,
            checkpoint=str(_latest_dir(output_dir)),
            early_stop_min_win_rate=cheap_teacher_min_win_rate,
        )
        cheap_teacher_eval = cheap_teacher_eval.model_copy(update={"passed": cheap_teacher_eval.win_rate >= cheap_teacher_min_win_rate})
        _save_json(_arena_path(output_dir, "teacher_cheap_eval"), cheap_teacher_eval.model_dump(mode="json"))
        if cheap_teacher_eval.passed:
            teacher_eval = evaluate_selfplay_policy_model(
                game_name=game_name,
                output_dir=output_dir,
                opponent="teacher",
                games=teacher_gate_games,
                checkpoint=str(_latest_dir(output_dir)),
                early_stop_min_win_rate=teacher_gate_min_win_rate,
            )
        else:
            teacher_eval = _make_arena_report(
                game_name=game_name,
                opponent="teacher",
                output_dir=output_dir,
                games=0,
                win_rate=status.last_teacher_win_rate,
                checkpoint_path=str(_latest_dir(output_dir) / "model.pt"),
                opponent_checkpoint=cheap_teacher_eval.opponent_checkpoint,
            )
            _save_json(_arena_path(output_dir, "teacher_eval"), teacher_eval.model_dump(mode="json"))
    else:
        teacher_eval = _make_arena_report(
            game_name=game_name,
            opponent="teacher",
            output_dir=output_dir,
            games=0,
            wins=0,
            losses=0,
            draws=0,
            win_rate=status.last_teacher_win_rate,
            passed=False,
            checkpoint_path=str(_latest_dir(output_dir) / "model.pt"),
            opponent_checkpoint="",
        )
        _save_json(_arena_path(output_dir, "teacher_eval"), teacher_eval.model_dump(mode="json"))
    if should_run_teacher:
        teacher_pass = teacher_eval.games > 0 and teacher_eval.win_rate >= teacher_gate_min_win_rate and quick_pass
        teacher_pass_streak = status.teacher_pass_streak + 1 if teacher_pass else 0
    else:
        teacher_pass = False
        teacher_pass_streak = status.teacher_pass_streak
    if teacher_pass:
        promoted = True
        best_checkpoint = _promote_latest_to_best(output_dir)
    else:
        best_checkpoint = status.best_checkpoint or str(_best_dir(output_dir) / "model.pt")

    new_state = SelfPlayStatusState(
        game=game_name,
        output_dir=output_dir,
        latest_checkpoint=str(_latest_dir(output_dir) / "model.pt"),
        best_checkpoint=best_checkpoint,
        replay_path=replay.output,
        replay_rows=replay.rows,
        selfplay_episodes=selfplay_episodes,
        train_epochs=status.train_epochs + max(int(epochs), 1) * learner_steps_per_phase,
        quick_gate_games=quick_gate_games,
        teacher_gate_games=teacher_gate_games,
        cheap_teacher_games=cheap_teacher_games,
        last_quick_win_rate=quick_eval.win_rate,
        last_cheap_teacher_win_rate=cheap_teacher_eval.win_rate,
        last_teacher_win_rate=teacher_eval.win_rate,
        teacher_pass_streak=teacher_pass_streak,
        best_history=status.best_history[-2:] + ([best_checkpoint] if promoted else []),
        replay_window_rounds=int(profile.get("replay_window_rounds", REPLAY_WINDOW_ROUNDS)),
        replay_window_rows=int(profile.get("replay_window_rows", REPLAY_WINDOW_ROWS)),
        recent_fraction=float(profile.get("recent_fraction", RECENT_REPLAY_FRACTION)),
        coverage={
            "unique_state_keys": replay.unique_state_keys,
            "unique_action_support": replay.unique_action_support,
            "duplicate_ratio": replay.duplicate_ratio,
            "mean_policy_entropy": replay.mean_policy_entropy,
            "step_depth_histogram": replay.step_depth_histogram,
        },
        persisted_repo=_policy_repo_id(repo_id),
        learner_updates=learner_updates,
        learner_steps_completed=status.learner_steps_completed + learner_steps_per_phase,
        phase_replay_rows=replay.rows,
        full_teacher_games_played=teacher_eval.games,
        evaluator_version=learner_updates,
        last_policy_loss=float(artifact.metrics.get("policy_loss", 0.0)),
        last_value_loss=float(artifact.metrics.get("value_loss", 0.0)),
        last_entropy=float(artifact.metrics.get("entropy", 0.0)),
        last_checkpoint_at=datetime.now(timezone.utc).isoformat(),
        last_replay_flush_at=heartbeat.last_replay_flush_at,
        autotuned_batch_size=effective_batch_size if autotune_batch_size else 0,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    _save_status(new_state)
    heartbeat = heartbeat.model_copy(
        update={
            "learner_updates": learner_updates,
            "learner_steps_completed": new_state.learner_steps_completed,
            "rows_consumed_total": new_state.replay_rows,
            "last_policy_loss": new_state.last_policy_loss,
            "last_value_loss": new_state.last_value_loss,
            "last_entropy": new_state.last_entropy,
            "last_quick_win_rate": new_state.last_quick_win_rate,
            "last_teacher_win_rate": new_state.last_teacher_win_rate,
            "phase": "sync" if learner_updates % max(int(sync_interval_updates), 1) == 0 else "replay",
            "checkpoint_version": new_state.evaluator_version,
            "last_checkpoint_at": new_state.last_checkpoint_at,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    gpu_util, gpu_mem = _gpu_snapshot()
    heartbeat = heartbeat.model_copy(update={"gpu_util_avg_5m": gpu_util, "gpu_mem_avg_5m": gpu_mem})
    _save_heartbeat(heartbeat)
    should_sync = promoted or learner_updates % max(int(sync_interval_updates), 1) == 0
    persisted_repo = (
        sync_selfplay_artifacts_to_hf(
            game_name=game_name,
            output_dir=output_dir,
            repo_id=repo_id,
        )
        if should_sync
        else ""
    )
    return SelfPlayTrainReport(
        game=game_name,
        output_dir=output_dir,
        latest_checkpoint=str(_latest_dir(output_dir) / "model.pt"),
        best_checkpoint=best_checkpoint,
        replay_path=replay.output,
        replay_rows=replay.rows,
        selfplay_episodes=selfplay_episodes,
        train_epochs=new_state.train_epochs,
        batch_size=effective_batch_size,
        device=artifact.device,
        quick_eval=quick_eval.model_copy(update={"passed": quick_pass}),
        cheap_teacher_eval=cheap_teacher_eval,
        teacher_eval=teacher_eval.model_copy(update={"passed": teacher_pass_streak >= teacher_gate_required_streak}),
        promoted=promoted,
        teacher_pass_streak=teacher_pass_streak,
        persisted_repo=persisted_repo,
        phase=phase,
        evaluator_version=new_state.evaluator_version,
        learner_steps_completed=learner_steps_per_phase,
    )


def train_selfplay_until_gate(
    *,
    game_name: str,
    output_dir: str,
    selfplay_episodes: int = 128,
    start_seed: int = 100000,
    simulations: int = 64,
    epochs: int = 5,
    batch_size: int = 1024,
    learning_rate: float = 3e-4,
    weight_decay: float = 1e-4,
    device: str = "",
    quick_gate_games: int = 50,
    quick_gate_min_win_rate: float | None = None,
    teacher_gate_games: int = 200,
    teacher_gate_min_win_rate: float | None = None,
    teacher_gate_required_streak: int | None = None,
    quick_gate_interval_updates: int | None = None,
    teacher_gate_interval_updates: int | None = None,
    sync_interval_updates: int | None = None,
    autotune_batch_size: bool = False,
    resume: bool = True,
    repo_id: str = "",
    max_rounds: int = 200,
) -> SelfPlayLongRunReport:
    required_streak = teacher_gate_required_streak if teacher_gate_required_streak is not None else 2
    required_win_rate = (
        teacher_gate_min_win_rate
        if teacher_gate_min_win_rate is not None
        else (0.90 if _is_perfect_info_game(game_name) else 0.60)
    )
    rounds_completed = 0
    last_report: SelfPlayTrainReport | None = None
    restore_first_round = resume
    while rounds_completed < max_rounds:
        report = train_selfplay_policy_model(
            game_name=game_name,
            output_dir=output_dir,
            selfplay_episodes=selfplay_episodes,
            start_seed=start_seed + rounds_completed * max(selfplay_episodes, 1),
            simulations=simulations,
            epochs=epochs,
            batch_size=batch_size,
            learning_rate=learning_rate,
            weight_decay=weight_decay,
            device=device,
            quick_gate_games=quick_gate_games,
            quick_gate_min_win_rate=quick_gate_min_win_rate,
            teacher_gate_games=teacher_gate_games,
            teacher_gate_min_win_rate=required_win_rate,
            teacher_gate_required_streak=required_streak,
            quick_gate_interval_updates=quick_gate_interval_updates,
            teacher_gate_interval_updates=teacher_gate_interval_updates,
            sync_interval_updates=sync_interval_updates,
            autotune_batch_size=autotune_batch_size,
            resume=restore_first_round,
            repo_id=repo_id,
        )
        rounds_completed += 1
        last_report = report
        restore_first_round = False
        teacher_win_rate = report.teacher_eval.win_rate if report.teacher_eval else 0.0
        if report.teacher_pass_streak >= required_streak and teacher_win_rate >= required_win_rate:
            return SelfPlayLongRunReport(
                game=game_name,
                output_dir=output_dir,
                completed=True,
                rounds_completed=rounds_completed,
                max_rounds=max_rounds,
                latest_checkpoint=report.latest_checkpoint,
                best_checkpoint=report.best_checkpoint,
                last_quick_win_rate=report.quick_eval.win_rate if report.quick_eval else 0.0,
                last_teacher_win_rate=teacher_win_rate,
                teacher_pass_streak=report.teacher_pass_streak,
                persisted_repo=report.persisted_repo,
                final_report=report,
                stop_reason="teacher_gate_passed",
            )
    if last_report is None:
        return SelfPlayLongRunReport(
            game=game_name,
            output_dir=output_dir,
            completed=False,
            rounds_completed=0,
            max_rounds=max_rounds,
            stop_reason="no_rounds_run",
        )
    return SelfPlayLongRunReport(
        game=game_name,
        output_dir=output_dir,
        completed=False,
        rounds_completed=rounds_completed,
        max_rounds=max_rounds,
        latest_checkpoint=last_report.latest_checkpoint,
        best_checkpoint=last_report.best_checkpoint,
        last_quick_win_rate=last_report.quick_eval.win_rate if last_report.quick_eval else 0.0,
        last_teacher_win_rate=last_report.teacher_eval.win_rate if last_report.teacher_eval else 0.0,
        teacher_pass_streak=last_report.teacher_pass_streak,
        persisted_repo=last_report.persisted_repo,
        final_report=last_report,
        stop_reason="max_rounds_exceeded",
    )


def resume_selfplay_policy_model(
    *,
    game_name: str,
    output_dir: str,
    selfplay_episodes: int = 128,
    start_seed: int = 100000,
    simulations: int = 64,
    epochs: int = 5,
    batch_size: int = 1024,
    learning_rate: float = 3e-4,
    weight_decay: float = 1e-4,
    device: str = "",
    quick_gate_games: int = 50,
    quick_gate_min_win_rate: float | None = None,
    teacher_gate_games: int = 200,
    teacher_gate_min_win_rate: float | None = None,
    teacher_gate_required_streak: int | None = None,
    quick_gate_interval_updates: int | None = None,
    teacher_gate_interval_updates: int | None = None,
    sync_interval_updates: int | None = None,
    autotune_batch_size: bool = False,
    repo_id: str = "",
) -> SelfPlayTrainReport:
    restore_selfplay_artifacts_from_hf(game_name=game_name, output_dir=output_dir, repo_id=repo_id)
    return train_selfplay_policy_model(
        game_name=game_name,
        output_dir=output_dir,
        selfplay_episodes=selfplay_episodes,
        start_seed=start_seed,
        simulations=simulations,
        epochs=epochs,
        batch_size=batch_size,
        learning_rate=learning_rate,
        weight_decay=weight_decay,
        device=device,
        quick_gate_games=quick_gate_games,
        quick_gate_min_win_rate=quick_gate_min_win_rate,
        teacher_gate_games=teacher_gate_games,
        teacher_gate_min_win_rate=teacher_gate_min_win_rate,
        teacher_gate_required_streak=teacher_gate_required_streak,
        quick_gate_interval_updates=quick_gate_interval_updates,
        teacher_gate_interval_updates=teacher_gate_interval_updates,
        sync_interval_updates=sync_interval_updates,
        autotune_batch_size=autotune_batch_size,
        resume=True,
        repo_id=repo_id,
    )


def selfplay_record(
    *,
    game_name: str,
    seed: int,
    model_dir: str,
) -> dict | None:
    import pyspiel

    checkpoint_dir = _resolve_policy_model_checkpoint(model_dir)
    artifact, model = load_policy_model(str(checkpoint_dir))
    torch, _, _ = _require_torch()
    model = model.to("cuda" if torch.cuda.is_available() else "cpu")

    random.seed(seed)
    np.random.seed(seed % (2**31))

    spec = resolve_game_trajectory_generator(game_name)
    game = pyspiel.load_game(game_name, spec.game_params)
    if game_name == "goofspiel":
        game = pyspiel.convert_to_turn_based(game)
    state = game.new_initial_state()
    bot_player = random.randint(0, game.num_players() - 1)

    runtime = _game_runtime()
    system_prompt = runtime["SYSTEM_PROMPT_TEMPLATE"].format(game_name=game_name, rules=runtime["GAME_RULES"][game_name])
    messages = [{"role": "system", "content": system_prompt}]

    move_count = 0
    while not state.is_terminal() and move_count < 500:
        if state.is_chance_node():
            outcomes = state.chance_outcomes()
            state.apply_action(random.choices([a for a, _ in outcomes], [p for _, p in outcomes])[0])
            continue

        player_id = state.current_player()
        legal = state.legal_actions(player_id)
        if player_id == bot_player:
            action = _model_action(model_artifact=artifact, model=model, state=state, player_id=player_id)
            if action not in legal:
                raise RuntimeError(f"{game_name} self-play policy model produced illegal action {action}")
            messages.append({"role": "user", "content": runtime["make_user_prompt"](state, player_id, legal, game_name)})
            messages.append({"role": "assistant", "content": str(action)})
            state.apply_action(action)
        else:
            state.apply_action(random.choice(legal))
        move_count += 1

    if not state.is_terminal() or len(messages) < 3:
        return None

    returns = list(state.returns())
    score = max(0.0, min(1.0, (_returns_to_value(returns, bot_player) + 1.0) / 2.0))
    if score < 0.5:
        return None

    config_id = random.randint(0, 99_999_999)
    return {
        "messages": messages,
        "env": "GAME",
        "source": "policy_model_selfplay",
        "game": game_name,
        "score": score,
        "task_id": runtime["GAME_IDX"][game_name] * 100_000_000 + config_id,
        "seed": seed,
    }
