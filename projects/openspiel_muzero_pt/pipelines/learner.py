from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch

from projects.openspiel_muzero_pt.games.action_codecs import get_action_codec
from projects.openspiel_muzero_pt.games.adapters import AffineOpenSpielAdapter
from projects.openspiel_muzero_pt.model.board_muzero import BoardMuZeroNet


def policy_cross_entropy(logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    log_probs = torch.log_softmax(logits, dim=-1)
    return -(target * log_probs).sum(dim=-1).mean()


@dataclass(slots=True)
class LearnerMetrics:
    loss: float
    policy_loss: float
    value_loss: float
    reward_loss: float
    recurrent_policy_loss: float
    recurrent_value_loss: float
    latent_loss: float


class OnlineLearner:
    def __init__(self, *, model: BoardMuZeroNet, adapter: AffineOpenSpielAdapter, optimizer: torch.optim.Optimizer, device):
        self.model = model
        self.adapter = adapter
        self.optimizer = optimizer
        self.device = torch.device(device)
        self.codec = get_action_codec(adapter.spec)

    def _masked_average(self, loss_per_row: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        mask = mask.to(loss_per_row.dtype)
        denom = torch.clamp(mask.sum(), min=1.0)
        return (loss_per_row * mask).sum() / denom

    def train_batch(self, batch: dict[str, np.ndarray]) -> LearnerMetrics:
        self.model.train()
        obs = torch.from_numpy(batch["obs"]).to(self.device)
        legal_mask = torch.from_numpy(batch["legal_mask"]).to(self.device)
        policy_target = torch.from_numpy(batch["policy_target"]).to(self.device)
        value_target = torch.from_numpy(batch["value_target"]).to(self.device)
        reward_target = torch.from_numpy(batch["reward_target"]).to(self.device)
        actions = torch.from_numpy(batch["action"]).to(self.device)
        next_obs = torch.from_numpy(batch["next_obs"]).to(self.device) if "next_obs" in batch else None
        next_legal_mask = torch.from_numpy(batch["next_legal_mask"]).to(self.device) if "next_legal_mask" in batch else None
        next_policy_target = (
            torch.from_numpy(batch["next_policy_target"]).to(self.device) if "next_policy_target" in batch else None
        )
        next_value_target = (
            torch.from_numpy(batch["next_value_target"]).to(self.device) if "next_value_target" in batch else None
        )
        recurrent_mask = (
            torch.from_numpy(batch["recurrent_mask"]).to(self.device)
            if "recurrent_mask" in batch
            else torch.zeros_like(reward_target, device=self.device)
        )

        initial = self.model.initial_inference(obs)
        masked_logits = initial.policy_logits.masked_fill(legal_mask <= 0, -1e9)
        loss_policy = policy_cross_entropy(masked_logits, policy_target)
        loss_value = torch.mean((initial.value - value_target) ** 2)

        action_planes = torch.cat(
            [
                self.codec.to_action_planes(int(action.item()), self.adapter.spec, device=self.device).unsqueeze(0)
                for action in actions
            ],
            dim=0,
        )
        recurrent = self.model.recurrent_inference(initial.latent, action_planes)
        loss_reward = torch.mean((recurrent.reward - reward_target) ** 2)
        loss_recurrent_policy = torch.zeros((), device=self.device)
        loss_recurrent_value = torch.zeros((), device=self.device)
        loss_latent = torch.zeros((), device=self.device)
        if next_obs is not None and next_legal_mask is not None and next_policy_target is not None and next_value_target is not None:
            valid_recurrent = recurrent_mask * (next_legal_mask.sum(dim=-1) > 0).to(recurrent_mask.dtype)
            with torch.no_grad():
                next_initial = self.model.initial_inference(next_obs)
            recurrent_masked_logits = recurrent.policy_logits.masked_fill(next_legal_mask <= 0, -1e9)
            recurrent_policy_per_row = -(next_policy_target * torch.log_softmax(recurrent_masked_logits, dim=-1)).sum(dim=-1)
            recurrent_value_per_row = (recurrent.value - next_value_target) ** 2
            latent_per_row = torch.mean((recurrent.latent - next_initial.latent.detach()) ** 2, dim=(1, 2, 3))
            loss_recurrent_policy = self._masked_average(recurrent_policy_per_row, valid_recurrent)
            loss_recurrent_value = self._masked_average(recurrent_value_per_row, valid_recurrent)
            loss_latent = self._masked_average(latent_per_row, valid_recurrent)

        loss = (
            loss_policy
            + loss_value
            + 0.25 * loss_reward
            + 0.5 * loss_recurrent_policy
            + 0.5 * loss_recurrent_value
            + 0.25 * loss_latent
        )
        self.optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
        self.optimizer.step()
        return LearnerMetrics(
            loss=float(loss.item()),
            policy_loss=float(loss_policy.item()),
            value_loss=float(loss_value.item()),
            reward_loss=float(loss_reward.item()),
            recurrent_policy_loss=float(loss_recurrent_policy.item()),
            recurrent_value_loss=float(loss_recurrent_value.item()),
            latent_loss=float(loss_latent.item()),
        )
