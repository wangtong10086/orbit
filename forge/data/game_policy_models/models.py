"""PyTorch policy-model training and artifact helpers for GAME."""

from __future__ import annotations

from pathlib import Path
import json

import numpy as np
from pydantic import Field

from forge.foundation.schema import FrozenModel


class PolicyModelArtifact(FrozenModel):
    game: str
    model_dir: str
    checkpoint_path: str
    dataset_path: str = ""
    input_dim: int
    action_dim: int
    hidden_dim: int = 256
    residual_blocks: int = 0
    batch_size: int = 512
    epochs: int = 10
    learning_rate: float = 1e-3
    weight_decay: float = 1e-4
    train_rows: int = 0
    device: str = ""
    model_kind: str = "policy"
    training_route: str = "imitation"
    layer_norm: bool = False
    metrics: dict[str, float] = Field(default_factory=dict)


class PolicyModelTrainReport(FrozenModel):
    game: str
    dataset_path: str
    output_dir: str
    checkpoint_path: str
    input_dim: int
    action_dim: int
    hidden_dim: int = 256
    residual_blocks: int = 0
    batch_size: int = 512
    epochs: int = 10
    learning_rate: float = 1e-3
    weight_decay: float = 1e-4
    train_rows: int = 0
    device: str = ""
    final_loss: float = 0.0
    accuracy: float = 0.0
    model_kind: str = "policy"
    training_route: str = "imitation"


def _require_torch():
    try:
        import torch
        import torch.nn as nn
        from torch.utils.data import DataLoader, TensorDataset
    except ImportError as exc:
        raise RuntimeError(
            "GAME policy-model training requires PyTorch. Install `torch` on the active environment or rental first."
        ) from exc
    return torch, nn, DataLoader, TensorDataset


def _metadata_path(model_dir: str | Path) -> Path:
    return Path(model_dir) / "metadata.json"


def _checkpoint_path(model_dir: str | Path) -> Path:
    return Path(model_dir) / "model.pt"


def _model_config_for_game(game_name: str) -> dict[str, object]:
    configs = {
        "leduc_poker": {"hidden_dim": 256, "residual_blocks": 3, "layer_norm": False},
        "liars_dice": {"hidden_dim": 256, "residual_blocks": 4, "layer_norm": False},
        "goofspiel": {"hidden_dim": 384, "residual_blocks": 4, "layer_norm": False},
        "gin_rummy": {"hidden_dim": 512, "residual_blocks": 6, "layer_norm": True},
    }
    return dict(configs.get(game_name, {"hidden_dim": 256, "residual_blocks": 2, "layer_norm": False}))


def default_selfplay_model_config(game_name: str) -> dict[str, object]:
    return _model_config_for_game(game_name)


def _build_policy_head(input_dim: int, hidden_dim: int, action_dim: int):
    torch, nn, _, _ = _require_torch()

    class GameActionMLP(nn.Module):
        def __init__(self):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(input_dim, hidden_dim),
                nn.ReLU(),
                nn.Linear(hidden_dim, hidden_dim),
                nn.ReLU(),
                nn.Linear(hidden_dim, action_dim),
            )

        def forward(self, x):
            return self.net(x)

    return GameActionMLP()


def _build_policy_value_model(
    input_dim: int,
    hidden_dim: int,
    action_dim: int,
    *,
    residual_blocks: int,
    layer_norm: bool,
):
    torch, nn, _, _ = _require_torch()

    class ResidualBlock(nn.Module):
        def __init__(self, width: int, use_layer_norm: bool):
            super().__init__()
            self.use_layer_norm = use_layer_norm
            self.fc1 = nn.Linear(width, width)
            self.fc2 = nn.Linear(width, width)
            self.norm1 = nn.LayerNorm(width) if use_layer_norm else nn.Identity()
            self.norm2 = nn.LayerNorm(width) if use_layer_norm else nn.Identity()
            self.act = nn.GELU()

        def forward(self, x):
            residual = x
            out = self.fc1(x)
            out = self.norm1(out)
            out = self.act(out)
            out = self.fc2(out)
            out = self.norm2(out)
            return self.act(out + residual)

    class PolicyValueResidualMLP(nn.Module):
        def __init__(self):
            super().__init__()
            self.input = nn.Linear(input_dim, hidden_dim)
            self.input_norm = nn.LayerNorm(hidden_dim) if layer_norm else nn.Identity()
            self.blocks = nn.ModuleList(
                ResidualBlock(hidden_dim, layer_norm) for _ in range(max(int(residual_blocks), 0))
            )
            self.policy_head = nn.Linear(hidden_dim, action_dim)
            self.value_head = nn.Linear(hidden_dim, 1)
            self.act = nn.GELU()

        def forward(self, x):
            hidden = self.act(self.input_norm(self.input(x)))
            for block in self.blocks:
                hidden = block(hidden)
            policy_logits = self.policy_head(hidden)
            value = self.value_head(hidden).squeeze(-1).tanh()
            return policy_logits, value

    return PolicyValueResidualMLP()


def build_policy_model_module(
    *,
    input_dim: int,
    hidden_dim: int,
    action_dim: int,
    model_kind: str = "policy",
    residual_blocks: int = 0,
    layer_norm: bool = False,
):
    if model_kind == "policy_value":
        return _build_policy_value_model(
            input_dim,
            hidden_dim,
            action_dim,
            residual_blocks=residual_blocks,
            layer_norm=layer_norm,
        )
    return _build_policy_head(input_dim, hidden_dim, action_dim)


def extract_policy_logits(model_output):
    if isinstance(model_output, tuple):
        return model_output[0]
    return model_output


def extract_value_predictions(model_output):
    if isinstance(model_output, tuple):
        return model_output[1]
    return None


def load_policy_model(model_dir: str):
    """Load a trained GAME policy model artifact and torch module."""

    torch, _, _, _ = _require_torch()
    root = Path(model_dir)
    metadata_path = _metadata_path(root)
    checkpoint_path = _checkpoint_path(root)
    if not metadata_path.exists() or not checkpoint_path.exists():
        raise FileNotFoundError(f"Missing policy-model artifact in {root}")
    metadata = PolicyModelArtifact.model_validate(json.loads(metadata_path.read_text(encoding="utf-8")))
    model = build_policy_model_module(
        input_dim=metadata.input_dim,
        hidden_dim=metadata.hidden_dim,
        action_dim=metadata.action_dim,
        model_kind=metadata.model_kind,
        residual_blocks=metadata.residual_blocks,
        layer_norm=metadata.layer_norm,
    )
    state = torch.load(checkpoint_path, map_location="cpu")
    model.load_state_dict(state)
    model.eval()
    return metadata, model


def train_policy_model(
    *,
    game_name: str,
    dataset_path: str,
    output_dir: str,
    hidden_dim: int = 256,
    batch_size: int = 512,
    epochs: int = 10,
    learning_rate: float = 1e-3,
    weight_decay: float = 1e-4,
    device: str = "",
) -> PolicyModelTrainReport:
    """Train a small per-game action model on structured expert rollouts."""

    torch, _, DataLoader, TensorDataset = _require_torch()

    payload = np.load(dataset_path)
    features = payload["features"].astype(np.float32)
    legal_masks = payload["legal_masks"].astype(np.float32)
    actions = payload["actions"].astype(np.int64)

    if features.ndim != 2:
        raise ValueError(f"Expected 2D features array, got shape={features.shape}")
    if legal_masks.ndim != 2:
        raise ValueError(f"Expected 2D legal_masks array, got shape={legal_masks.shape}")
    if actions.ndim != 1:
        raise ValueError(f"Expected 1D actions array, got shape={actions.shape}")
    if len(features) == 0:
        raise ValueError("Expert dataset is empty")

    resolved_device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    model = build_policy_model_module(
        input_dim=int(features.shape[1]),
        hidden_dim=hidden_dim,
        action_dim=int(legal_masks.shape[1]),
        model_kind="policy",
        residual_blocks=0,
        layer_norm=False,
    ).to(resolved_device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=weight_decay)

    dataset = TensorDataset(
        torch.from_numpy(features),
        torch.from_numpy(legal_masks),
        torch.from_numpy(actions),
    )
    loader = DataLoader(dataset, batch_size=min(batch_size, len(dataset)), shuffle=True)

    final_loss = 0.0
    final_accuracy = 0.0

    for _ in range(max(epochs, 1)):
        model.train()
        total_loss = 0.0
        total_correct = 0
        total_seen = 0
        for batch_features, batch_masks, batch_actions in loader:
            batch_features = batch_features.to(resolved_device)
            batch_masks = batch_masks.to(resolved_device)
            batch_actions = batch_actions.to(resolved_device)

            logits = extract_policy_logits(model(batch_features))
            masked_logits = logits.masked_fill(batch_masks <= 0, -1e9)
            loss = torch.nn.functional.cross_entropy(masked_logits, batch_actions)

            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()

            total_loss += float(loss.detach().cpu()) * int(batch_actions.shape[0])
            predictions = masked_logits.argmax(dim=1)
            total_correct += int((predictions == batch_actions).sum().item())
            total_seen += int(batch_actions.shape[0])

        if total_seen:
            final_loss = total_loss / total_seen
            final_accuracy = total_correct / total_seen

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    checkpoint_path = _checkpoint_path(root)
    torch.save(model.state_dict(), checkpoint_path)

    artifact = PolicyModelArtifact(
        game=game_name,
        model_dir=str(root),
        checkpoint_path=str(checkpoint_path),
        dataset_path=dataset_path,
        input_dim=int(features.shape[1]),
        action_dim=int(legal_masks.shape[1]),
        hidden_dim=hidden_dim,
        residual_blocks=0,
        batch_size=batch_size,
        epochs=max(epochs, 1),
        learning_rate=learning_rate,
        weight_decay=weight_decay,
        train_rows=int(actions.shape[0]),
        device=resolved_device,
        model_kind="policy",
        training_route="imitation",
        layer_norm=False,
        metrics={"final_loss": final_loss, "accuracy": final_accuracy},
    )
    _metadata_path(root).write_text(
        json.dumps(artifact.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return PolicyModelTrainReport(
        game=game_name,
        dataset_path=dataset_path,
        output_dir=str(root),
        checkpoint_path=str(checkpoint_path),
        input_dim=artifact.input_dim,
        action_dim=artifact.action_dim,
        hidden_dim=hidden_dim,
        residual_blocks=0,
        batch_size=batch_size,
        epochs=max(epochs, 1),
        learning_rate=learning_rate,
        weight_decay=weight_decay,
        train_rows=artifact.train_rows,
        device=resolved_device,
        final_loss=final_loss,
        accuracy=final_accuracy,
        model_kind="policy",
        training_route="imitation",
    )
