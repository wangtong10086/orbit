from __future__ import annotations

from dataclasses import dataclass
import itertools
from typing import Protocol

import numpy as np
import torch

from projects.openspiel_muzero_pt.model.board_muzero import BoardMuZeroNet
from projects.openspiel_muzero_pt.runtime.shared_memory import InferenceWorkerSharedBuffers


@dataclass(frozen=True, slots=True)
class InferenceBatch:
    latent: np.ndarray
    policy_logits: np.ndarray
    value: np.ndarray


@dataclass(frozen=True, slots=True)
class RecurrentInferenceBatch:
    latent: np.ndarray
    reward: np.ndarray
    policy_logits: np.ndarray
    value: np.ndarray


class ModelInferenceClient(Protocol):
    def initial(self, obs_batch: np.ndarray) -> InferenceBatch: ...

    def recurrent(self, latent_batch: np.ndarray, action_planes_batch: np.ndarray) -> RecurrentInferenceBatch: ...


class LocalModelInferenceClient:
    def __init__(self, *, model: BoardMuZeroNet, device: torch.device | str):
        self.model = model
        self.device = torch.device(device)

    @torch.no_grad()
    def initial(self, obs_batch: np.ndarray) -> InferenceBatch:
        obs = torch.from_numpy(np.asarray(obs_batch, dtype=np.float32)).to(self.device)
        output = self.model.initial_inference(obs)
        return InferenceBatch(
            latent=output.latent.detach().cpu().numpy().astype(np.float32, copy=False),
            policy_logits=output.policy_logits.detach().cpu().numpy().astype(np.float32, copy=False),
            value=output.value.detach().cpu().numpy().astype(np.float32, copy=False),
        )

    @torch.no_grad()
    def recurrent(self, latent_batch: np.ndarray, action_planes_batch: np.ndarray) -> RecurrentInferenceBatch:
        latent = torch.from_numpy(np.asarray(latent_batch, dtype=np.float32)).to(self.device)
        action_planes = torch.from_numpy(np.asarray(action_planes_batch, dtype=np.float32)).to(self.device)
        output = self.model.recurrent_inference(latent, action_planes)
        return RecurrentInferenceBatch(
            latent=output.latent.detach().cpu().numpy().astype(np.float32, copy=False),
            reward=output.reward.detach().cpu().numpy().astype(np.float32, copy=False),
            policy_logits=output.policy_logits.detach().cpu().numpy().astype(np.float32, copy=False),
            value=output.value.detach().cpu().numpy().astype(np.float32, copy=False),
        )


class BrokeredInferenceClient:
    def __init__(self, *, worker_id: int, request_queue, response_queue, shared_buffers_meta):
        self.worker_id = int(worker_id)
        self.request_queue = request_queue
        self.response_queue = response_queue
        self.shared_buffers = InferenceWorkerSharedBuffers.attach(shared_buffers_meta)
        self._request_ids = itertools.count()

    def _roundtrip(self, kind: str, *, batch_size: int) -> dict[str, np.ndarray]:
        request_id = int(next(self._request_ids))
        self.request_queue.put(
            {
                "worker_id": self.worker_id,
                "request_id": request_id,
                "kind": kind,
                "batch_size": int(batch_size),
            }
        )
        while True:
            response = self.response_queue.get()
            if int(response.get("request_id", -1)) != request_id:
                continue
            if str(response.get("status", "ok")) != "ok":
                raise RuntimeError(f"Inference request failed: {response.get('error')}")
            response_batch_size = int(response.get("batch_size", batch_size))
            if kind == "initial":
                return self.shared_buffers.read_initial_response(response_batch_size)
            if kind == "recurrent":
                return self.shared_buffers.read_recurrent_response(response_batch_size)
            raise KeyError(f"Unsupported inference kind: {kind}")

    def initial(self, obs_batch: np.ndarray) -> InferenceBatch:
        batch_size = self.shared_buffers.write_initial_request(obs_batch)
        response = self._roundtrip("initial", batch_size=batch_size)
        return InferenceBatch(
            latent=response["latent"],
            policy_logits=response["policy_logits"],
            value=response["value"],
        )

    def recurrent(self, latent_batch: np.ndarray, action_planes_batch: np.ndarray) -> RecurrentInferenceBatch:
        batch_size = self.shared_buffers.write_recurrent_request(latent_batch, action_planes_batch)
        response = self._roundtrip("recurrent", batch_size=batch_size)
        return RecurrentInferenceBatch(
            latent=response["latent"],
            reward=response["reward"],
            policy_logits=response["policy_logits"],
            value=response["value"],
        )
