"""Inference helpers for PyTorch GAME action-model sampling."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from forge.data.game_policy_models.featurizers import extract_state_features, legal_action_mask
from forge.data.game_policy_models.models import (
    PolicyModelArtifact,
    extract_policy_logits,
    load_policy_model,
)
from forge.foundation.schema import FrozenModel


MODEL_ROOT = Path(__file__).resolve().parents[3] / "artifacts" / "game_policy_models"


class PolicyModelStatusEntry(FrozenModel):
    game: str
    model_dir: str
    exists: bool = False
    reason: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)


def default_policy_model_dir(game_name: str) -> str:
    return str(MODEL_ROOT / game_name / "default")


def resolve_policy_model_dir(model_dir: str) -> str:
    root = Path(model_dir)
    for candidate in (root / "best", root, root / "latest"):
        if (candidate / "metadata.json").exists() and (candidate / "model.pt").exists():
            return str(candidate)
    return str(root)


def policy_model_status(*, game_name: str, model_dir: str) -> PolicyModelStatusEntry:
    root = Path(model_dir)
    latest = root / "latest"
    best = root / "best"
    resolved = Path(resolve_policy_model_dir(str(root)))
    metadata_path = resolved / "metadata.json"
    model_path = resolved / "model.pt"
    if not metadata_path.exists() or not model_path.exists():
        return PolicyModelStatusEntry(
            game=game_name,
            model_dir=str(root),
            exists=False,
            reason="policy model artifact missing",
        )
    artifact = PolicyModelArtifact.model_validate_json(metadata_path.read_text(encoding="utf-8"))
    return PolicyModelStatusEntry(
        game=game_name,
        model_dir=str(root),
        exists=True,
        metadata={
            **artifact.model_dump(mode="json"),
            "resolved_model_dir": str(resolved),
            "best_exists": (best / "metadata.json").exists() and (best / "model.pt").exists(),
            "latest_exists": (latest / "metadata.json").exists() and (latest / "model.pt").exists(),
        },
    )


def select_policy_model_action(
    *,
    artifact: PolicyModelArtifact,
    model,
    game,
    state,
    player_id: int,
) -> int:
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("Selecting actions from GAME policy models requires PyTorch") from exc

    features = extract_state_features(state, player_id)
    mask = legal_action_mask(game, state, player_id)
    device = next(model.parameters()).device
    with torch.no_grad():
        feature_tensor = torch.from_numpy(features).float().to(device).unsqueeze(0)
        mask_tensor = torch.from_numpy(mask).float().to(device).unsqueeze(0)
        logits = extract_policy_logits(model(feature_tensor))
        masked_logits = logits.masked_fill(mask_tensor <= 0, -1e9)
        action = int(masked_logits.argmax(dim=1).item())
    if mask[action] <= 0:
        raise RuntimeError("Policy model selected an illegal action")
    return action
