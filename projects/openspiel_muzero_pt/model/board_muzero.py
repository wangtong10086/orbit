from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import nn


@dataclass(frozen=True, slots=True)
class BoardMuZeroConfig:
    input_channels: int
    board_height: int
    board_width: int
    action_dim: int
    channels: int = 128
    repr_blocks: int = 10
    dyn_blocks: int = 4
    head_hidden: int = 256


@dataclass(slots=True)
class InitialOutput:
    latent: torch.Tensor
    policy_logits: torch.Tensor
    value: torch.Tensor


@dataclass(slots=True)
class RecurrentOutput:
    latent: torch.Tensor
    reward: torch.Tensor
    policy_logits: torch.Tensor
    value: torch.Tensor


class ResidualBlock(nn.Module):
    def __init__(self, channels: int):
        super().__init__()
        self.conv1 = nn.Conv2d(channels, channels, kernel_size=3, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(channels)
        self.conv2 = nn.Conv2d(channels, channels, kernel_size=3, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(channels)
        self.act = nn.GELU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        residual = x
        out = self.act(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        return self.act(out + residual)


class ResidualTower(nn.Module):
    def __init__(self, width_in: int, channels: int, blocks: int):
        super().__init__()
        self.stem = nn.Sequential(
            nn.Conv2d(width_in, channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(channels),
            nn.GELU(),
        )
        self.blocks = nn.Sequential(*(ResidualBlock(channels) for _ in range(max(int(blocks), 0))))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        hidden = self.stem(x)
        return self.blocks(hidden)


class PredictionHead(nn.Module):
    def __init__(self, channels: int, board_height: int, board_width: int, action_dim: int, head_hidden: int):
        super().__init__()
        flat_dim = channels * board_height * board_width
        self.policy = nn.Sequential(
            nn.Conv2d(channels, 2, kernel_size=1),
            nn.Flatten(),
            nn.Linear(2 * board_height * board_width, head_hidden),
            nn.GELU(),
            nn.Linear(head_hidden, action_dim),
        )
        self.value = nn.Sequential(
            nn.Flatten(),
            nn.Linear(flat_dim, head_hidden),
            nn.GELU(),
            nn.Linear(head_hidden, 1),
            nn.Tanh(),
        )

    def forward(self, latent: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        policy_logits = self.policy(latent)
        value = self.value(latent).squeeze(-1)
        return policy_logits, value


class RewardHead(nn.Module):
    def __init__(self, channels: int, board_height: int, board_width: int, head_hidden: int):
        super().__init__()
        flat_dim = channels * board_height * board_width
        self.net = nn.Sequential(
            nn.Flatten(),
            nn.Linear(flat_dim, head_hidden),
            nn.GELU(),
            nn.Linear(head_hidden, 1),
            nn.Tanh(),
        )

    def forward(self, latent: torch.Tensor) -> torch.Tensor:
        return self.net(latent).squeeze(-1)


def _scale_norm(x: torch.Tensor) -> torch.Tensor:
    """Normalize latent to unit max-norm per sample, avoiding tanh saturation."""
    flat = x.flatten(1)
    scale = flat.abs().amax(dim=1, keepdim=True).clamp(min=1.0)
    return (flat / scale).view_as(x)


class BoardMuZeroNet(nn.Module):
    def __init__(self, config: BoardMuZeroConfig):
        super().__init__()
        self.config = config
        self.representation_tower = ResidualTower(
            width_in=config.input_channels,
            channels=config.channels,
            blocks=config.repr_blocks,
        )
        self.dynamics_tower = ResidualTower(
            width_in=config.channels + 3,
            channels=config.channels,
            blocks=config.dyn_blocks,
        )
        self.repr_norm = nn.LayerNorm([config.channels, config.board_height, config.board_width])
        self.dyn_norm = nn.LayerNorm([config.channels, config.board_height, config.board_width])
        self.prediction_head = PredictionHead(
            channels=config.channels,
            board_height=config.board_height,
            board_width=config.board_width,
            action_dim=config.action_dim,
            head_hidden=config.head_hidden,
        )
        self.reward_head = RewardHead(
            channels=config.channels,
            board_height=config.board_height,
            board_width=config.board_width,
            head_hidden=config.head_hidden,
        )

    def representation(self, obs: torch.Tensor) -> torch.Tensor:
        h = self.representation_tower(obs)
        return _scale_norm(self.repr_norm(h))

    def dynamics(self, latent: torch.Tensor, action_planes: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        h = self.dynamics_tower(torch.cat([latent, action_planes], dim=1))
        next_latent = _scale_norm(self.dyn_norm(h))
        reward = self.reward_head(next_latent)
        return next_latent, reward

    def prediction(self, latent: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        return self.prediction_head(latent)

    def initial_inference(self, obs: torch.Tensor) -> InitialOutput:
        latent = self.representation(obs)
        policy_logits, value = self.prediction(latent)
        return InitialOutput(latent=latent, policy_logits=policy_logits, value=value)

    def recurrent_inference(self, latent: torch.Tensor, action_planes: torch.Tensor) -> RecurrentOutput:
        # Scale gradient entering dynamics by 0.5 (MuZero Appendix G).
        # This prevents the dynamics tower from dominating representation learning.
        scaled_latent = latent * 0.5 + latent.detach() * 0.5
        next_latent, reward = self.dynamics(scaled_latent, action_planes)
        policy_logits, value = self.prediction(next_latent)
        return RecurrentOutput(latent=next_latent, reward=reward, policy_logits=policy_logits, value=value)
