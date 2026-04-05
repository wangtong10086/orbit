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
    def __init__(
        self,
        *,
        model: BoardMuZeroNet,
        adapter: AffineOpenSpielAdapter,
        optimizer: torch.optim.Optimizer,
        device,
        reward_loss_weight: float = 0.05,
        recurrent_policy_loss_weight: float = 0.5,
        recurrent_value_loss_weight: float = 0.5,
        latent_loss_weight: float = 0.25,
    ):
        self.model = model
        self.adapter = adapter
        self.optimizer = optimizer
        self.device = torch.device(device)
        self.codec = get_action_codec(adapter.spec)
        self.reward_loss_weight = float(reward_loss_weight)
        self.recurrent_policy_loss_weight = float(recurrent_policy_loss_weight)
        self.recurrent_value_loss_weight = float(recurrent_value_loss_weight)
        self.latent_loss_weight = float(latent_loss_weight)

    def _masked_average(self, loss_per_row: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        mask = mask.to(loss_per_row.dtype)
        denom = torch.clamp(mask.sum(), min=1.0)
        return (loss_per_row * mask).sum() / denom

    def _slice_batch(self, batch: dict[str, np.ndarray], start: int, stop: int) -> dict[str, np.ndarray]:
        return {key: value[start:stop] for key, value in batch.items()}

    def _teacher_kl_loss(self, batch: dict[str, np.ndarray]) -> torch.Tensor:
        """KL(teacher || model) on expert rows — anchors the model to teacher policy."""
        obs = torch.from_numpy(batch["obs"]).to(self.device)
        legal_mask = torch.from_numpy(batch["legal_mask"]).to(self.device)
        teacher_policy = torch.from_numpy(batch["policy_target"]).to(self.device)
        initial = self.model.initial_inference(obs)
        masked_logits = initial.policy_logits.masked_fill(legal_mask <= 0, -1e9)
        model_log_probs = torch.log_softmax(masked_logits, dim=-1)
        # KL(teacher || model) = sum(teacher * log(teacher / model))
        # = sum(teacher * log(teacher)) - sum(teacher * log(model))
        # The first term is constant w.r.t. model, so we minimize -sum(teacher * log(model))
        # which is just cross-entropy. But true KL includes the entropy term for logging.
        teacher_log = torch.log(teacher_policy.clamp(min=1e-8))
        kl_per_row = (teacher_policy * (teacher_log - model_log_probs)).sum(dim=-1)
        return kl_per_row.mean()

    def _compute_losses(self, batch: dict[str, np.ndarray]) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
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

        action_planes = self.codec.batch_action_planes(actions, self.adapter.spec, device=self.device)
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
            + self.reward_loss_weight * loss_reward
            + self.recurrent_policy_loss_weight * loss_recurrent_policy
            + self.recurrent_value_loss_weight * loss_recurrent_value
            + self.latent_loss_weight * loss_latent
        )
        return loss, {
            "loss": loss,
            "policy_loss": loss_policy,
            "value_loss": loss_value,
            "reward_loss": loss_reward,
            "recurrent_policy_loss": loss_recurrent_policy,
            "recurrent_value_loss": loss_recurrent_value,
            "latent_loss": loss_latent,
        }

    def train_batch(self, batch: dict[str, np.ndarray], *, microbatch_size: int | None = None) -> LearnerMetrics:
        self.model.train()
        self.optimizer.zero_grad(set_to_none=True)
        total_rows = int(batch["action"].shape[0])
        if microbatch_size is None or microbatch_size <= 0 or microbatch_size >= total_rows:
            loss, metrics_tensors = self._compute_losses(batch)
            loss.backward()
            metrics = {key: float(value.item()) for key, value in metrics_tensors.items()}
        else:
            microbatch_size = max(int(microbatch_size), 1)
            metrics = {
                "loss": 0.0,
                "policy_loss": 0.0,
                "value_loss": 0.0,
                "reward_loss": 0.0,
                "recurrent_policy_loss": 0.0,
                "recurrent_value_loss": 0.0,
                "latent_loss": 0.0,
            }
            for start in range(0, total_rows, microbatch_size):
                stop = min(start + microbatch_size, total_rows)
                weight = float(stop - start) / float(total_rows)
                loss, metrics_tensors = self._compute_losses(self._slice_batch(batch, start, stop))
                (loss * weight).backward()
                for key, value in metrics_tensors.items():
                    metrics[key] += float(value.item()) * weight
        torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
        self.optimizer.step()
        return LearnerMetrics(
            loss=float(metrics["loss"]),
            policy_loss=float(metrics["policy_loss"]),
            value_loss=float(metrics["value_loss"]),
            reward_loss=float(metrics["reward_loss"]),
            recurrent_policy_loss=float(metrics["recurrent_policy_loss"]),
            recurrent_value_loss=float(metrics["recurrent_value_loss"]),
            latent_loss=float(metrics["latent_loss"]),
        )
