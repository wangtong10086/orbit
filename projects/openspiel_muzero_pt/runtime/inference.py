from __future__ import annotations

from dataclasses import dataclass
import itertools
from typing import Protocol

import numpy as np
import torch

from projects.openspiel_muzero_pt.model.board_muzero import BoardMuZeroNet


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
    def __init__(self, *, worker_id: int, request_queue, response_queue):
        self.worker_id = int(worker_id)
        self.request_queue = request_queue
        self.response_queue = response_queue
        self._request_ids = itertools.count()

    def _roundtrip(self, kind: str, payload: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        request_id = int(next(self._request_ids))
        self.request_queue.put(
            {
                "worker_id": self.worker_id,
                "request_id": request_id,
                "kind": kind,
                "payload": payload,
            }
        )
        while True:
            response = self.response_queue.get()
            if int(response.get("request_id", -1)) != request_id:
                continue
            if str(response.get("status", "ok")) != "ok":
                raise RuntimeError(f"Inference request failed: {response.get('error')}")
            return response["payload"]

    def initial(self, obs_batch: np.ndarray) -> InferenceBatch:
        response = self._roundtrip(
            "initial",
            {"obs": np.asarray(obs_batch, dtype=np.float32)},
        )
        return InferenceBatch(
            latent=response["latent"],
            policy_logits=response["policy_logits"],
            value=response["value"],
        )

    def recurrent(self, latent_batch: np.ndarray, action_planes_batch: np.ndarray) -> RecurrentInferenceBatch:
        response = self._roundtrip(
            "recurrent",
            {
                "latent": np.asarray(latent_batch, dtype=np.float32),
                "action_planes": np.asarray(action_planes_batch, dtype=np.float32),
            },
        )
        return RecurrentInferenceBatch(
            latent=response["latent"],
            reward=response["reward"],
            policy_logits=response["policy_logits"],
            value=response["value"],
        )
