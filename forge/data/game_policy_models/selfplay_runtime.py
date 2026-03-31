"""Runtime helpers for GAME self-play replay generation."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import multiprocessing as mp
from pathlib import Path
import queue
import threading
import time
import zlib

import numpy as np

from forge.data.game_policy_models.artifacts import PERFECT_INFO_GAMES, _runtime_profile
from forge.data.game_policy_models.featurizers import extract_state_features, legal_action_mask
from forge.data.game_policy_models.models import (
    PolicyModelArtifact,
    extract_policy_logits,
    extract_value_predictions,
    load_policy_model,
)


def _require_torch():
    try:
        import torch
        from torch.utils.data import DataLoader, TensorDataset
    except ImportError as exc:
        raise RuntimeError(
            "GAME self-play training requires PyTorch. Install `torch` on the active environment or rental first."
        ) from exc
    return torch, DataLoader, TensorDataset


def _is_perfect_info_game(game_name: str) -> bool:
    return game_name in PERFECT_INFO_GAMES


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


def _state_key(state, player_id: int) -> str:
    try:
        text = str(state.information_state_string(player_id))
    except Exception:
        try:
            text = str(state.observation_string(player_id))
        except Exception:
            text = str(extract_state_features(state, player_id).tolist())
    return f"{player_id}:{zlib.adler32(text.encode('utf-8'))}"


@dataclass
class _PredictSlot:
    event: threading.Event
    result: tuple[np.ndarray, float] | None = None
    error: BaseException | None = None


@dataclass
class _BatchedPredictRequest:
    state: object
    player_id: int
    cache_key: tuple[int, str]
    slot: _PredictSlot


@dataclass
class _TensorPredictRequest:
    features: np.ndarray
    legal_mask: np.ndarray
    reply_conn: object


_PROCESS_SHARED_PREDICTOR_CLIENTS: dict[str, "_ProcessSharedPredictorClient"] | None = None


def _predict_many_states(*, model, requests: list[tuple[object, int]], action_dim: int) -> list[tuple[np.ndarray, float]]:
    del action_dim
    torch, _, _ = _require_torch()
    model.eval()
    device = next(model.parameters()).device
    features_list = []
    masks_list = []
    for state, player_id in requests:
        features_list.append(extract_state_features(state, player_id))
        masks_list.append(legal_action_mask(state.get_game(), state, player_id))
    with torch.no_grad():
        feature_tensor = torch.from_numpy(np.stack(features_list).astype(np.float32)).to(device)
        mask_tensor = torch.from_numpy(np.stack(masks_list).astype(np.float32)).to(device)
        output = model(feature_tensor)
        logits = extract_policy_logits(output)
        values = extract_value_predictions(output)
        masked_logits = logits.masked_fill(mask_tensor <= 0, -1e9)
        priors = torch.softmax(masked_logits, dim=1).detach().cpu().numpy()
        value_array = values.detach().cpu().numpy() if values is not None else np.zeros(len(requests), dtype=np.float32)
    return [(priors[idx].astype(np.float32), float(value_array[idx])) for idx in range(len(requests))]


def _predict_many_tensors(*, model, features_list: list[np.ndarray], masks_list: list[np.ndarray]) -> list[tuple[np.ndarray, float]]:
    torch, _, _ = _require_torch()
    model.eval()
    device = next(model.parameters()).device
    with torch.no_grad():
        feature_tensor = torch.from_numpy(np.stack(features_list).astype(np.float32)).to(device)
        mask_tensor = torch.from_numpy(np.stack(masks_list).astype(np.float32)).to(device)
        output = model(feature_tensor)
        logits = extract_policy_logits(output)
        values = extract_value_predictions(output)
        masked_logits = logits.masked_fill(mask_tensor <= 0, -1e9)
        priors = torch.softmax(masked_logits, dim=1).detach().cpu().numpy()
        value_array = values.detach().cpu().numpy() if values is not None else np.zeros(len(features_list), dtype=np.float32)
    return [(priors[idx].astype(np.float32), float(value_array[idx])) for idx in range(len(features_list))]


class _NeuralSearchEvaluator:
    def __init__(self, *, artifact: PolicyModelArtifact, model, action_dim: int):
        self.artifact = artifact
        self.model = model
        self.action_dim = action_dim
        self._cache: OrderedDict[tuple[int, str], tuple[np.ndarray, float]] = OrderedDict()
        self._cache_limit = 2048

    def _predict_many(self, requests: list[tuple[object, int]]) -> list[tuple[np.ndarray, float]]:
        return _predict_many_states(model=self.model, requests=requests, action_dim=self.action_dim)

    def _predict(self, state, player_id: int) -> tuple[np.ndarray, float]:
        cache_key = (player_id, _state_key(state, player_id))
        cached = self._cache.get(cache_key)
        if cached is not None:
            self._cache.move_to_end(cache_key)
            return cached
        result = self._predict_many([(state, player_id)])[0]
        self._cache[cache_key] = result
        if len(self._cache) > self._cache_limit:
            self._cache.popitem(last=False)
        return result

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


class _SharedBatchedPredictor:
    def __init__(
        self,
        *,
        artifact: PolicyModelArtifact,
        model,
        action_dim: int,
        max_batch_size: int,
        max_queue_latency_ms: float,
    ):
        self.artifact = artifact
        self.model = model
        self.action_dim = action_dim
        self.max_batch_size = max(int(max_batch_size), 1)
        self.max_queue_latency_s = max(float(max_queue_latency_ms), 0.1) / 1000.0
        self._queue: queue.Queue[_BatchedPredictRequest | None] = queue.Queue()
        self._cache: OrderedDict[tuple[int, str], tuple[np.ndarray, float]] = OrderedDict()
        self._cache_limit = 4096
        self._cache_lock = threading.Lock()
        self._closed = False
        self._worker = threading.Thread(target=self._run, name=f"game-eval-{artifact.game}", daemon=True)
        self._worker.start()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._queue.put(None)
        self._worker.join(timeout=5)

    def predict_many(self, requests: list[tuple[object, int]]) -> list[tuple[np.ndarray, float]]:
        if not requests:
            return []
        results: list[tuple[np.ndarray, float] | None] = [None] * len(requests)
        pending: list[tuple[int, _BatchedPredictRequest]] = []
        for idx, (state, player_id) in enumerate(requests):
            cache_key = (player_id, _state_key(state, player_id))
            cached = self._cache_get(cache_key)
            if cached is not None:
                results[idx] = cached
                continue
            slot = _PredictSlot(event=threading.Event())
            request = _BatchedPredictRequest(
                state=state,
                player_id=player_id,
                cache_key=cache_key,
                slot=slot,
            )
            pending.append((idx, request))
            self._queue.put(request)
        for idx, request in pending:
            request.slot.event.wait()
            if request.slot.error is not None:
                raise request.slot.error
            results[idx] = request.slot.result
        return [result for result in results if result is not None]

    def _cache_get(self, cache_key: tuple[int, str]) -> tuple[np.ndarray, float] | None:
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached is not None:
                self._cache.move_to_end(cache_key)
            return cached

    def _cache_put(self, cache_key: tuple[int, str], result: tuple[np.ndarray, float]) -> None:
        with self._cache_lock:
            self._cache[cache_key] = result
            if len(self._cache) > self._cache_limit:
                self._cache.popitem(last=False)

    def _run(self) -> None:
        while True:
            request = self._queue.get()
            if request is None:
                return
            batch = [request]
            deadline = time.perf_counter() + self.max_queue_latency_s
            while len(batch) < self.max_batch_size:
                timeout = deadline - time.perf_counter()
                if timeout <= 0:
                    break
                try:
                    next_request = self._queue.get(timeout=timeout)
                except queue.Empty:
                    break
                if next_request is None:
                    self._queue.put(None)
                    break
                batch.append(next_request)
            try:
                predictions = _predict_many_states(
                    model=self.model,
                    requests=[(item.state, item.player_id) for item in batch],
                    action_dim=self.action_dim,
                )
                for item, prediction in zip(batch, predictions, strict=False):
                    self._cache_put(item.cache_key, prediction)
                    item.slot.result = prediction
                    item.slot.event.set()
            except BaseException as exc:
                for item in batch:
                    item.slot.error = exc
                    item.slot.event.set()


class _QueuedBatchedPredictorServer:
    def __init__(
        self,
        *,
        artifact: PolicyModelArtifact,
        model,
        request_queue,
        max_batch_size: int,
        max_queue_latency_ms: float,
    ):
        self.artifact = artifact
        self.model = model
        self.request_queue = request_queue
        self.max_batch_size = max(int(max_batch_size), 1)
        self.max_queue_latency_s = max(float(max_queue_latency_ms), 0.1) / 1000.0
        self._closed = False
        self._worker = threading.Thread(target=self._run, name=f"game-eval-queue-{artifact.game}", daemon=True)
        self._worker.start()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.request_queue.put(None)
        self._worker.join(timeout=5)

    def _run(self) -> None:
        while True:
            request = self.request_queue.get()
            if request is None:
                return
            batch = [request]
            deadline = time.perf_counter() + self.max_queue_latency_s
            while len(batch) < self.max_batch_size:
                timeout = deadline - time.perf_counter()
                if timeout <= 0:
                    break
                try:
                    next_request = self.request_queue.get(timeout=timeout)
                except queue.Empty:
                    break
                if next_request is None:
                    self.request_queue.put(None)
                    break
                batch.append(next_request)
            try:
                predictions = _predict_many_tensors(
                    model=self.model,
                    features_list=[item.features for item in batch],
                    masks_list=[item.legal_mask for item in batch],
                )
                for item, prediction in zip(batch, predictions, strict=False):
                    item.reply_conn.send(prediction)
                    item.reply_conn.close()
            except BaseException as exc:
                for item in batch:
                    item.reply_conn.send(exc)
                    item.reply_conn.close()


class _ProcessSharedPredictorClient:
    def __init__(self, request_queue):
        self.request_queue = request_queue
        self._cache: OrderedDict[tuple[int, str], tuple[np.ndarray, float]] = OrderedDict()
        self._cache_limit = 4096

    def predict(self, state, player_id: int) -> tuple[np.ndarray, float]:
        cache_key = (player_id, _state_key(state, player_id))
        cached = self._cache.get(cache_key)
        if cached is not None:
            self._cache.move_to_end(cache_key)
            return cached
        recv_conn, send_conn = mp.Pipe(duplex=False)
        request = _TensorPredictRequest(
            features=extract_state_features(state, player_id),
            legal_mask=legal_action_mask(state.get_game(), state, player_id),
            reply_conn=send_conn,
        )
        self.request_queue.put(request)
        response = recv_conn.recv()
        recv_conn.close()
        if isinstance(response, BaseException):
            raise response
        self._cache[cache_key] = response
        if len(self._cache) > self._cache_limit:
            self._cache.popitem(last=False)
        return response


def _process_predictor_client(checkpoint_dir: str) -> _ProcessSharedPredictorClient:
    if _PROCESS_SHARED_PREDICTOR_CLIENTS is None:
        raise RuntimeError("Process predictor clients were not initialized")
    return _PROCESS_SHARED_PREDICTOR_CLIENTS[checkpoint_dir]


class _ProcessSharedSearchEvaluator:
    def __init__(self, *, predictor: _ProcessSharedPredictorClient, action_dim: int):
        self.predictor = predictor
        self.action_dim = action_dim

    def _predict_many(self, requests: list[tuple[object, int]]) -> list[tuple[np.ndarray, float]]:
        return [self.predictor.predict(state, player_id) for state, player_id in requests]

    def _predict(self, state, player_id: int) -> tuple[np.ndarray, float]:
        return self.predictor.predict(state, player_id)

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


class _SharedSearchEvaluator:
    def __init__(self, *, artifact: PolicyModelArtifact, predictor: _SharedBatchedPredictor, action_dim: int):
        self.artifact = artifact
        self.predictor = predictor
        self.action_dim = action_dim

    def _predict_many(self, requests: list[tuple[object, int]]) -> list[tuple[np.ndarray, float]]:
        return self.predictor.predict_many(requests)

    def _predict(self, state, player_id: int) -> tuple[np.ndarray, float]:
        return self._predict_many([(state, player_id)])[0]

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


def _materialize_replay_model(game_name: str, artifact: PolicyModelArtifact, model):
    del game_name
    torch, _, _ = _require_torch()
    resolved_device = "cuda" if torch.cuda.is_available() else "cpu"
    if hasattr(torch, "set_float32_matmul_precision"):
        torch.set_float32_matmul_precision("high")
    model = model.to(resolved_device)
    if resolved_device == "cuda" and artifact.architecture == "resnet" and hasattr(torch, "channels_last"):
        model = model.to(memory_format=torch.channels_last)
    model.eval()
    return model


def _shared_predictor_batch_size(game_name: str) -> int:
    profile = _runtime_profile(game_name)
    if "shared_eval_batch_size" in profile:
        return max(int(profile["shared_eval_batch_size"]), 1)
    if _is_perfect_info_game(game_name):
        micro_batch = int(profile.get("replay_micro_batch_size", 16))
        concurrency = int(profile.get("gpu_actor_concurrency", 2))
        return max(micro_batch * max(concurrency, 1), micro_batch)
    return int(profile.get("shared_eval_batch_size", 32))


def _shared_predictor_latency_ms(game_name: str) -> float:
    profile = _runtime_profile(game_name)
    if "shared_eval_latency_ms" in profile:
        return max(float(profile["shared_eval_latency_ms"]), 0.1)
    if _is_perfect_info_game(game_name):
        return 2.0
    return 4.0


def _build_shared_predictor_pool(*, game_name: str, checkpoint_dirs: list[str], action_dim: int) -> dict[str, _SharedBatchedPredictor]:
    pool: dict[str, _SharedBatchedPredictor] = {}
    for checkpoint_dir in checkpoint_dirs:
        artifact, model = _load_checkpoint_dir(Path(checkpoint_dir))
        materialized = _materialize_replay_model(game_name, artifact, model)
        pool[checkpoint_dir] = _SharedBatchedPredictor(
            artifact=artifact,
            model=materialized,
            action_dim=action_dim,
            max_batch_size=_shared_predictor_batch_size(game_name),
            max_queue_latency_ms=_shared_predictor_latency_ms(game_name),
        )
    return pool


def _build_process_predictor_pool(*, game_name: str, checkpoint_dirs: list[str], action_dim: int, mp_context) -> tuple[dict[str, object], dict[str, _QueuedBatchedPredictorServer]]:
    queues: dict[str, object] = {}
    servers: dict[str, _QueuedBatchedPredictorServer] = {}
    for checkpoint_dir in checkpoint_dirs:
        artifact, model = _load_checkpoint_dir(Path(checkpoint_dir))
        materialized = _materialize_replay_model(game_name, artifact, model)
        request_queue = mp_context.Queue()
        queues[checkpoint_dir] = request_queue
        servers[checkpoint_dir] = _QueuedBatchedPredictorServer(
            artifact=artifact,
            model=materialized,
            request_queue=request_queue,
            max_batch_size=_shared_predictor_batch_size(game_name),
            max_queue_latency_ms=_shared_predictor_latency_ms(game_name),
        )
    return queues, servers


def _init_process_predictor_clients(shared_queues: dict[str, object]) -> None:
    global _PROCESS_SHARED_PREDICTOR_CLIENTS
    _PROCESS_SHARED_PREDICTOR_CLIENTS = {
        checkpoint_dir: _ProcessSharedPredictorClient(request_queue)
        for checkpoint_dir, request_queue in shared_queues.items()
    }


__all__ = [
    "_NeuralSearchEvaluator",
    "_ProcessSharedSearchEvaluator",
    "_SharedBatchedPredictor",
    "_SharedSearchEvaluator",
    "_build_process_predictor_pool",
    "_build_shared_predictor_pool",
    "_init_process_predictor_clients",
    "_load_checkpoint_dir",
    "_materialize_replay_model",
    "_normalize_policy",
    "_process_predictor_client",
    "_shared_predictor_batch_size",
    "_shared_predictor_latency_ms",
    "_state_key",
]
