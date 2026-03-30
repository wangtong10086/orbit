"""Self-play training for imperfect-information GAME policy models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import random
import shutil
import zlib

import numpy as np
from pydantic import Field

from forge.config import ForgeConfig
from forge.data.game_generators.base import ensure_game_scripts_path
from forge.data.game_generators.policy_generators import (
    LoadedPolicySnapshot,
    build_policy_snapshot,
    load_policy_snapshot,
)
from forge.data.game_policy_models.featurizers import (
    extract_state_features,
    feature_spec_for_game,
    legal_action_mask,
)
from forge.data.game_policy_models.models import (
    PolicyModelArtifact,
    build_policy_model_module,
    default_selfplay_model_config,
    extract_policy_logits,
    extract_value_predictions,
    load_policy_model,
)
from forge.data.game_trajectory_generators import resolve_game_trajectory_generator
from forge.foundation.schema import FrozenModel


ensure_game_scripts_path()

from generate_v11 import GAME_IDX, GAME_RULES, SYSTEM_PROMPT_TEMPLATE, make_user_prompt  # type: ignore  # noqa: E402


class ReplayBufferReport(FrozenModel):
    game: str
    output: str
    episodes: int = 0
    rows: int = 0
    input_dim: int = 0
    action_dim: int = 0
    simulations: int = 0
    generator_family: str = ""
    unique_state_keys: int = 0
    unique_action_support: int = 0
    duplicate_ratio: float = 0.0
    mean_policy_entropy: float = 0.0
    step_depth_histogram: dict[str, int] = Field(default_factory=dict)


class ArenaEvalReport(FrozenModel):
    game: str
    opponent: str
    output: str = ""
    games: int = 0
    wins: int = 0
    losses: int = 0
    draws: int = 0
    win_rate: float = 0.0
    passed: bool = False
    checkpoint_path: str = ""
    opponent_checkpoint: str = ""


class SelfPlayTrainReport(FrozenModel):
    game: str
    output_dir: str
    latest_checkpoint: str = ""
    best_checkpoint: str = ""
    replay_path: str = ""
    replay_rows: int = 0
    selfplay_episodes: int = 0
    train_epochs: int = 0
    batch_size: int = 0
    device: str = ""
    quick_eval: ArenaEvalReport | None = None
    teacher_eval: ArenaEvalReport | None = None
    promoted: bool = False
    teacher_pass_streak: int = 0
    persisted_repo: str = ""
    training_route: str = "selfplay"


class SelfPlayStatusEntry(FrozenModel):
    game: str
    output_dir: str
    exists: bool = False
    latest_exists: bool = False
    best_exists: bool = False
    status: dict[str, object] = Field(default_factory=dict)
    latest_metadata: dict[str, object] = Field(default_factory=dict)
    best_metadata: dict[str, object] = Field(default_factory=dict)
    persisted_repo: str = ""


class SelfPlayStatusState(FrozenModel):
    game: str
    output_dir: str
    training_route: str = "selfplay"
    latest_checkpoint: str = ""
    best_checkpoint: str = ""
    replay_path: str = ""
    replay_rows: int = 0
    selfplay_episodes: int = 0
    train_epochs: int = 0
    quick_gate_games: int = 50
    teacher_gate_games: int = 200
    last_quick_win_rate: float = 0.0
    last_teacher_win_rate: float = 0.0
    teacher_pass_streak: int = 0
    best_history: list[str] = Field(default_factory=list)
    replay_window_rounds: int = 20
    replay_window_rows: int = 50000
    recent_fraction: float = 0.7
    coverage: dict[str, object] = Field(default_factory=dict)
    persisted_repo: str = ""
    updated_at: str = ""


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


def _root_dir(output_dir: str) -> Path:
    return Path(output_dir)


def _latest_dir(output_dir: str) -> Path:
    return _root_dir(output_dir) / "latest"


def _best_dir(output_dir: str) -> Path:
    return _root_dir(output_dir) / "best"


def _history_dir(output_dir: str) -> Path:
    return _root_dir(output_dir) / "history"


def _arena_dir(output_dir: str) -> Path:
    return _root_dir(output_dir) / "arena"


def _status_path(output_dir: str) -> Path:
    return _root_dir(output_dir) / "status.json"


def _replay_path(output_dir: str) -> Path:
    return _root_dir(output_dir) / "replay_meta" / "latest_replay.npz"


def _replay_meta_path(output_dir: str) -> Path:
    return _root_dir(output_dir) / "replay_meta" / "latest.json"


def _arena_path(output_dir: str, name: str) -> Path:
    return _arena_dir(output_dir) / f"{name}.json"


def _policy_repo_id(repo_id: str = "") -> str:
    config = ForgeConfig.load()
    return repo_id or config.hf_game_policy_repo or config.hf_game_teacher_repo


def _ensure_dirs(output_dir: str) -> None:
    for path in (
        _root_dir(output_dir),
        _latest_dir(output_dir),
        _best_dir(output_dir),
        _history_dir(output_dir),
        _arena_dir(output_dir),
        _replay_meta_path(output_dir).parent,
    ):
        path.mkdir(parents=True, exist_ok=True)


def _save_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _history_checkpoint_dir(output_dir: str) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return _history_dir(output_dir) / stamp


REPLAY_WINDOW_ROUNDS = 20
REPLAY_WINDOW_ROWS = 50_000
RECENT_REPLAY_FRACTION = 0.7


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


def _normalize_policy(policy: np.ndarray, legal_mask: np.ndarray) -> np.ndarray:
    masked = np.asarray(policy, dtype=np.float32) * np.asarray(legal_mask, dtype=np.float32)
    total = float(masked.sum())
    if total <= 0:
        legal = np.asarray(legal_mask, dtype=np.float32)
        legal_total = float(legal.sum())
        if legal_total <= 0:
            raise RuntimeError("No legal actions available while normalizing search policy")
        return legal / legal_total
    return masked / total


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


def _state_key(state, player_id: int) -> str:
    try:
        text = str(state.information_state_string(player_id))
    except Exception:
        try:
            text = str(state.observation_string(player_id))
        except Exception:
            text = str(extract_state_features(state, player_id).tolist())
    return f"{player_id}:{zlib.adler32(text.encode('utf-8'))}"


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
        model=model,
        metrics={},
    )
    best_dir = _best_dir(output_dir)
    best_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_latest_dir(output_dir) / "model.pt", best_dir / "model.pt")
    shutil.copy2(_latest_dir(output_dir) / "metadata.json", best_dir / "metadata.json")
    return artifact, model


class _NeuralSearchEvaluator:
    def __init__(self, *, artifact: PolicyModelArtifact, model, action_dim: int):
        self.artifact = artifact
        self.model = model
        self.action_dim = action_dim

    def _predict(self, state, player_id: int) -> tuple[np.ndarray, float]:
        torch, _, _ = _require_torch()
        self.model.eval()
        device = next(self.model.parameters()).device
        features = extract_state_features(state, player_id)
        mask = legal_action_mask(state.get_game(), state, player_id)
        with torch.no_grad():
            feature_tensor = torch.from_numpy(features).float().to(device).unsqueeze(0)
            mask_tensor = torch.from_numpy(mask).float().to(device).unsqueeze(0)
            output = self.model(feature_tensor)
            logits = extract_policy_logits(output)
            values = extract_value_predictions(output)
            masked_logits = logits.masked_fill(mask_tensor <= 0, -1e9)
            priors = torch.softmax(masked_logits, dim=1).squeeze(0).detach().cpu().numpy()
            value = float(values.squeeze(0).detach().cpu().item()) if values is not None else 0.0
        return priors.astype(np.float32), value

    def evaluate(self, state):
        if state.is_terminal():
            return list(state.returns())
        if state.is_chance_node():
            return [0.0 for _ in range(state.get_game().num_players())]
        player_id = state.current_player()
        if player_id < 0:
            return [0.0 for _ in range(state.get_game().num_players())]
        _, value = self._predict(state, player_id)
        players = state.get_game().num_players()
        if players == 2:
            return [value, -value] if player_id == 0 else [-value, value]
        values = [0.0 for _ in range(players)]
        values[player_id] = value
        return values

    def prior(self, state):
        if state.is_chance_node():
            return [(action, float(prob)) for action, prob in state.chance_outcomes()]
        player_id = state.current_player()
        if player_id < 0:
            legal = state.legal_actions()
            weight = 1.0 / max(len(legal), 1)
            return [(action, weight) for action in legal]
        priors, _ = self._predict(state, player_id)
        legal = state.legal_actions(player_id)
        normalized = _normalize_policy(priors, legal_action_mask(state.get_game(), state, player_id))
        return [(action, float(normalized[action])) for action in legal]


def _load_checkpoint_dir(path: Path) -> tuple[PolicyModelArtifact, object]:
    return load_policy_model(str(path))


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


def _compatible_checkpoint_pool(*, output_dir: str, input_dim: int, action_dim: int) -> list[Path]:
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
        ):
            compatible.append(candidate)
    return compatible


def _round_replay_dir(output_dir: str) -> Path:
    path = _replay_meta_path(output_dir).parent / "rounds"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _round_replay_path(output_dir: str) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return _round_replay_dir(output_dir) / f"round-{stamp}.npz"


def _load_replay_arrays(path: Path) -> dict[str, np.ndarray]:
    payload = np.load(path)
    return {key: payload[key] for key in payload.files}


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
            "created_at": datetime.now(UTC).isoformat(),
        },
    )
    return round_path


def _merge_recent_replay_window(
    *,
    output_dir: str,
    rng_seed: int,
    max_rounds: int = REPLAY_WINDOW_ROUNDS,
    max_rows: int = REPLAY_WINDOW_ROWS,
    recent_fraction: float = RECENT_REPLAY_FRACTION,
) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(rng_seed)
    round_paths = sorted(_round_replay_dir(output_dir).glob("round-*.npz"))
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


def build_selfplay_replay(
    *,
    game_name: str,
    output_dir: str,
    episodes: int,
    start_seed: int,
    simulations: int,
) -> ReplayBufferReport:
    _require_search()
    _ensure_dirs(output_dir)
    game = _base_selfplay_game(game_name)
    action_dim = int(game.num_distinct_actions())
    feature_probe_state = game.new_initial_state()
    input_dim = int(extract_state_features(feature_probe_state, 0 if game.num_players() else 0).shape[0])
    pool = _compatible_checkpoint_pool(output_dir=output_dir, input_dim=input_dim, action_dim=action_dim)
    if not pool:
        _build_empty_policy_artifact(game_name, output_dir)
        pool = _compatible_checkpoint_pool(output_dir=output_dir, input_dim=input_dim, action_dim=action_dim)
    loaded_models: dict[str, tuple[PolicyModelArtifact, object]] = {}
    rows: list[_ReplayRow] = []
    rng = random.Random(start_seed)

    for episode_id in range(max(int(episodes), 1)):
        checkpoint_dir = rng.choice(pool)
        if str(checkpoint_dir) not in loaded_models:
            loaded_models[str(checkpoint_dir)] = _load_checkpoint_dir(checkpoint_dir)
        artifact, model = loaded_models[str(checkpoint_dir)]
        evaluator = _NeuralSearchEvaluator(artifact=artifact, model=model, action_dim=action_dim)
        search = (
            PuctSearch(evaluator=evaluator, simulations=simulations, c_puct=1.5, root_noise=True)
            if game_name == "goofspiel"
            else ImperfectInfoPuctSearch(evaluator=evaluator, simulations=simulations, c_puct=1.25, root_noise=True)
        )

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
            policy_target = _apply_dirichlet_noise(policy_target, mask)
            features = extract_state_features(state, player_id)
            action = _sample_action_from_policy(policy_target, mask, temperature=_resolve_temperature(step_index))
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
        raise RuntimeError(f"GAME self-play replay generation produced no rows for {game_name}")

    features = np.stack([row.features for row in rows]).astype(np.float32)
    legal_masks = np.stack([row.legal_mask for row in rows]).astype(np.float32)
    policy_targets = np.stack([row.policy_target for row in rows]).astype(np.float32)
    value_targets = np.asarray([row.value_target for row in rows], dtype=np.float32)
    player_ids = np.asarray([row.player_id for row in rows], dtype=np.int64)
    game_steps = np.asarray([row.game_step for row in rows], dtype=np.int64)
    episode_ids = np.asarray([row.episode_id for row in rows], dtype=np.int64)
    state_keys = np.asarray([row.state_key for row in rows], dtype=f"<U{max(len(row.state_key) for row in rows)}")

    current_payload = {
        "features": features,
        "legal_masks": legal_masks,
        "policy_targets": policy_targets,
        "value_targets": value_targets,
        "player_ids": player_ids,
        "game_steps": game_steps,
        "episode_ids": episode_ids,
        "state_keys": state_keys,
    }
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
    duplicate_ratio = 1.0 - (unique_state_keys / max(len(state_keys), 1))
    coverage = {
        "unique_state_keys": unique_state_keys,
        "unique_action_support": len(supported_actions),
        "duplicate_ratio": duplicate_ratio,
        "mean_policy_entropy": float(sum(entropies) / max(len(entropies), 1)),
        "step_depth_histogram": depth_hist,
    }
    _persist_round_replay(
        output_dir=output_dir,
        game_name=game_name,
        payload=current_payload,
        simulations=simulations,
        coverage=coverage,
    )
    merged_payload = _merge_recent_replay_window(
        output_dir=output_dir,
        rng_seed=start_seed + episodes + simulations,
        max_rounds=REPLAY_WINDOW_ROUNDS,
        max_rows=REPLAY_WINDOW_ROWS,
        recent_fraction=RECENT_REPLAY_FRACTION,
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
            "replay_window_rounds": REPLAY_WINDOW_ROUNDS,
            "replay_window_rows": REPLAY_WINDOW_ROWS,
            "recent_fraction": RECENT_REPLAY_FRACTION,
            "coverage": coverage,
            "updated_at": datetime.now(UTC).isoformat(),
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
        generator_family="puct" if game_name == "goofspiel" else "imperfect_puct",
        unique_state_keys=unique_state_keys,
        unique_action_support=len(supported_actions),
        duplicate_ratio=duplicate_ratio,
        mean_policy_entropy=float(sum(entropies) / max(len(entropies), 1)),
        step_depth_histogram=depth_hist,
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
    resolved_device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    layer_norm = bool(config["layer_norm"])
    residual_blocks = int(config["residual_blocks"])
    hidden_dim = int(config["hidden_dim"])

    latest_dir = _latest_dir(output_dir)
    should_reinit = True
    if (latest_dir / "metadata.json").exists() and (latest_dir / "model.pt").exists():
        loaded_artifact, loaded_model = load_policy_model(str(latest_dir))
        if (
            loaded_artifact.training_route == "selfplay"
            and loaded_artifact.model_kind == "policy_value"
            and loaded_artifact.input_dim == int(features.shape[1])
            and loaded_artifact.action_dim == int(legal_masks.shape[1])
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
        ).to(resolved_device)

    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=weight_decay)
    dataset = TensorDataset(
        torch.from_numpy(features),
        torch.from_numpy(legal_masks),
        torch.from_numpy(policy_targets),
        torch.from_numpy(value_targets),
    )
    loader = DataLoader(dataset, batch_size=min(batch_size, len(dataset)), shuffle=True)
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
    if opponent == "teacher":
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
    for game_idx in range(max(int(games), 1)):
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
                if opponent == "teacher":
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

    report = ArenaEvalReport(
        game=game_name,
        opponent=opponent,
        output=str(_arena_path(output_dir, f"{opponent}_eval")),
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


def _promote_latest_to_best(output_dir: str) -> str:
    latest = _latest_dir(output_dir)
    best = _best_dir(output_dir)
    best.mkdir(parents=True, exist_ok=True)
    history_target = _history_checkpoint_dir(output_dir)
    history_target.mkdir(parents=True, exist_ok=True)
    if (best / "model.pt").exists():
        for name in ("model.pt", "metadata.json"):
            source = best / name
            if source.exists():
                shutil.copy2(source, history_target / name)
    for name in ("model.pt", "metadata.json"):
        shutil.copy2(latest / name, best / name)
    return str(best / "model.pt")


def _load_status(output_dir: str, game_name: str) -> SelfPlayStatusState:
    status_file = _status_path(output_dir)
    if not status_file.exists():
        return SelfPlayStatusState(game=game_name, output_dir=output_dir)
    return SelfPlayStatusState.model_validate_json(status_file.read_text(encoding="utf-8"))


def _save_status(state: SelfPlayStatusState) -> None:
    _status_path(state.output_dir).write_text(
        json.dumps(state.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def sync_selfplay_artifacts_to_hf(*, game_name: str, output_dir: str, repo_id: str = "", token: str = "") -> str:
    resolved_repo = _policy_repo_id(repo_id)
    if not resolved_repo:
        return ""
    try:
        from huggingface_hub import HfApi
    except ImportError:
        return ""

    api = HfApi(token=token or ForgeConfig.load().hf_token)
    api.create_repo(repo_id=resolved_repo, repo_type="model", private=True, exist_ok=True)
    for local_path, remote_path in (
        (_status_path(output_dir), f"checkpoints/{game_name}/status.json"),
        (_latest_dir(output_dir) / "model.pt", f"checkpoints/{game_name}/latest/model.pt"),
        (_latest_dir(output_dir) / "metadata.json", f"checkpoints/{game_name}/latest/metadata.json"),
        (_best_dir(output_dir) / "model.pt", f"checkpoints/{game_name}/best/model.pt"),
        (_best_dir(output_dir) / "metadata.json", f"checkpoints/{game_name}/best/metadata.json"),
        (_arena_path(output_dir, "quick_eval"), f"arena/{game_name}/quick_eval.json"),
        (_arena_path(output_dir, "teacher_eval"), f"arena/{game_name}/teacher_eval.json"),
        (_replay_meta_path(output_dir), f"replay_meta/{game_name}/latest.json"),
    ):
        if not local_path.exists():
            continue
        api.upload_file(
            path_or_fileobj=str(local_path),
            path_in_repo=remote_path,
            repo_id=resolved_repo,
            repo_type="model",
            commit_message=f"Update self-play artifacts for {game_name}",
        )
    return resolved_repo


def restore_selfplay_artifacts_from_hf(*, game_name: str, output_dir: str, repo_id: str = "", token: str = "") -> bool:
    resolved_repo = _policy_repo_id(repo_id)
    if not resolved_repo:
        return False
    try:
        from huggingface_hub import HfApi, hf_hub_download
    except ImportError:
        return False

    api = HfApi(token=token or ForgeConfig.load().hf_token)
    try:
        files = api.list_repo_files(repo_id=resolved_repo, repo_type="model")
    except Exception:
        return False
    prefix_map = {
        f"checkpoints/{game_name}/status.json": _status_path(output_dir),
        f"checkpoints/{game_name}/latest/model.pt": _latest_dir(output_dir) / "model.pt",
        f"checkpoints/{game_name}/latest/metadata.json": _latest_dir(output_dir) / "metadata.json",
        f"checkpoints/{game_name}/best/model.pt": _best_dir(output_dir) / "model.pt",
        f"checkpoints/{game_name}/best/metadata.json": _best_dir(output_dir) / "metadata.json",
        f"arena/{game_name}/quick_eval.json": _arena_path(output_dir, "quick_eval"),
        f"arena/{game_name}/teacher_eval.json": _arena_path(output_dir, "teacher_eval"),
        f"replay_meta/{game_name}/latest.json": _replay_meta_path(output_dir),
    }
    restored = False
    for repo_file, local_target in prefix_map.items():
        if repo_file not in files:
            continue
        local_target.parent.mkdir(parents=True, exist_ok=True)
        downloaded = hf_hub_download(
            repo_id=resolved_repo,
            filename=repo_file,
            repo_type="model",
            token=token or ForgeConfig.load().hf_token,
        )
        shutil.copy2(downloaded, local_target)
        restored = True
    return restored


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
    quick_gate_min_win_rate: float = 0.52,
    teacher_gate_games: int = 200,
    teacher_gate_min_win_rate: float = 0.60,
    teacher_gate_required_streak: int = 2,
    resume: bool = True,
    repo_id: str = "",
) -> SelfPlayTrainReport:
    _ensure_dirs(output_dir)
    if resume:
        restore_selfplay_artifacts_from_hf(game_name=game_name, output_dir=output_dir, repo_id=repo_id)
    status = _load_status(output_dir, game_name)
    replay = build_selfplay_replay(
        game_name=game_name,
        output_dir=output_dir,
        episodes=selfplay_episodes,
        start_seed=start_seed + status.train_epochs,
        simulations=simulations,
    )
    artifact = _train_from_replay(
        game_name=game_name,
        replay_path=replay.output,
        output_dir=output_dir,
        epochs=epochs,
        batch_size=batch_size,
        learning_rate=learning_rate,
        weight_decay=weight_decay,
        device=device,
    )
    promoted = False
    if (_best_dir(output_dir) / "metadata.json").exists():
        quick_eval = evaluate_selfplay_policy_model(
            game_name=game_name,
            output_dir=output_dir,
            opponent="best",
            games=quick_gate_games,
            checkpoint=str(_latest_dir(output_dir)),
        )
    else:
        quick_eval = ArenaEvalReport(
            game=game_name,
            opponent="best",
            output=str(_arena_path(output_dir, "quick_eval")),
            games=0,
            wins=0,
            losses=0,
            draws=0,
            win_rate=1.0,
            passed=True,
            checkpoint_path=str(_latest_dir(output_dir) / "model.pt"),
            opponent_checkpoint="",
        )
        _save_json(_arena_path(output_dir, "quick_eval"), quick_eval.model_dump(mode="json"))

    quick_pass = quick_eval.win_rate >= quick_gate_min_win_rate
    teacher_eval = evaluate_selfplay_policy_model(
        game_name=game_name,
        output_dir=output_dir,
        opponent="teacher",
        games=teacher_gate_games,
        checkpoint=str(_latest_dir(output_dir)),
    )
    teacher_pass = teacher_eval.win_rate >= teacher_gate_min_win_rate and quick_pass
    teacher_pass_streak = status.teacher_pass_streak + 1 if teacher_pass else 0
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
        train_epochs=status.train_epochs + max(int(epochs), 1),
        quick_gate_games=quick_gate_games,
        teacher_gate_games=teacher_gate_games,
        last_quick_win_rate=quick_eval.win_rate,
        last_teacher_win_rate=teacher_eval.win_rate,
        teacher_pass_streak=teacher_pass_streak,
        best_history=status.best_history[-2:] + ([best_checkpoint] if promoted else []),
        replay_window_rounds=REPLAY_WINDOW_ROUNDS,
        replay_window_rows=REPLAY_WINDOW_ROWS,
        recent_fraction=RECENT_REPLAY_FRACTION,
        coverage={
            "unique_state_keys": replay.unique_state_keys,
            "unique_action_support": replay.unique_action_support,
            "duplicate_ratio": replay.duplicate_ratio,
            "mean_policy_entropy": replay.mean_policy_entropy,
            "step_depth_histogram": replay.step_depth_histogram,
        },
        persisted_repo=_policy_repo_id(repo_id),
        updated_at=datetime.now(UTC).isoformat(),
    )
    _save_status(new_state)
    persisted_repo = sync_selfplay_artifacts_to_hf(
        game_name=game_name,
        output_dir=output_dir,
        repo_id=repo_id,
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
        batch_size=batch_size,
        device=artifact.device,
        quick_eval=quick_eval.model_copy(update={"passed": quick_pass}),
        teacher_eval=teacher_eval.model_copy(update={"passed": teacher_pass_streak >= teacher_gate_required_streak}),
        promoted=promoted,
        teacher_pass_streak=teacher_pass_streak,
        persisted_repo=persisted_repo,
    )


def selfplay_status(*, game_name: str, output_dir: str) -> SelfPlayStatusEntry:
    root = Path(output_dir)
    status_file = _status_path(output_dir)
    latest_dir = _latest_dir(output_dir)
    best_dir = _best_dir(output_dir)
    latest_metadata: dict[str, object] = {}
    best_metadata: dict[str, object] = {}
    if (latest_dir / "metadata.json").exists():
        latest_metadata = _load_json(latest_dir / "metadata.json")
    if (best_dir / "metadata.json").exists():
        best_metadata = _load_json(best_dir / "metadata.json")
    payload = _load_json(status_file) if status_file.exists() else {}
    return SelfPlayStatusEntry(
        game=game_name,
        output_dir=str(root),
        exists=status_file.exists(),
        latest_exists=(latest_dir / "metadata.json").exists() and (latest_dir / "model.pt").exists(),
        best_exists=(best_dir / "metadata.json").exists() and (best_dir / "model.pt").exists(),
        status=payload,
        latest_metadata=latest_metadata,
        best_metadata=best_metadata,
        persisted_repo=str(payload.get("persisted_repo", "")),
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
    quick_gate_min_win_rate: float = 0.52,
    teacher_gate_games: int = 200,
    teacher_gate_min_win_rate: float = 0.60,
    teacher_gate_required_streak: int = 2,
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

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(game_name=game_name, rules=GAME_RULES[game_name])
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
            messages.append({"role": "user", "content": make_user_prompt(state, player_id, legal, game_name)})
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
        "task_id": GAME_IDX[game_name] * 100_000_000 + config_id,
        "seed": seed,
    }
