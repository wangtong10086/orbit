"""Inference helpers for PyTorch GAME action-model sampling.

Includes ``play_record`` for generating a single winning game trajectory
by having the trained policy model play as one player (teacher inference).
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from forge.data.game_policy_models.featurizers import extract_state_features, legal_action_mask
from forge.data.game_policy_models.models import (
    PolicyModelArtifact,
    extract_policy_logits,
    load_policy_model,
)
from forge.foundation.schema import FrozenModel

if TYPE_CHECKING:
    pass


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


def play_record(
    *,
    game_name: str,
    seed: int,
    model_dir: str,
) -> dict | None:
    """Play a single game using the teacher policy model and record the trajectory.

    The policy model plays as one randomly-chosen player; the opponent uses random
    legalmoves.  Returns a ``dict`` with ``messages`` suitable for SFT, or ``None``
    if the model lost or the game did not finish cleanly.
    """
    try:
        import pyspiel  # type: ignore
        import torch
    except ImportError as exc:
        raise RuntimeError("play_record requires pyspiel and torch") from exc

    from forge.data.game_generators.base import ensure_game_scripts_path

    ensure_game_scripts_path()
    from generate_v11 import GAME_IDX, GAME_RULES, SYSTEM_PROMPT_TEMPLATE, make_user_prompt  # type: ignore

    checkpoint_dir = resolve_policy_model_dir(model_dir)
    artifact, model = load_policy_model(str(checkpoint_dir))
    model = model.to("cuda" if torch.cuda.is_available() else "cpu")

    random.seed(seed)
    np.random.seed(seed % (2**31))

    from forge.data.game_trajectory_generators import resolve_game_trajectory_generator

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
            action = select_policy_model_action(
                artifact=artifact,
                model=model,
                game=game,
                state=state,
                player_id=player_id,
            )
            if action not in legal:
                raise RuntimeError(f"{game_name} policy model produced illegal action {action}")
            messages.append({"role": "user", "content": make_user_prompt(state, player_id, legal, game_name)})
            messages.append({"role": "assistant", "content": str(action)})
            state.apply_action(action)
        else:
            state.apply_action(random.choice(legal))
        move_count += 1

    if not state.is_terminal() or len(messages) < 3:
        return None

    returns = list(state.returns())
    raw_value = returns[bot_player] if (returns[bot_player] != 0 or len(set(returns)) == 1) else -1.0
    score = max(0.0, min(1.0, (raw_value + 1.0) / 2.0))
    if score < 0.5:
        return None

    config_id = random.randint(0, 99_999_999)
    return {
        "messages": messages,
        "env": "GAME",
        "source": "policy_model_teacher",
        "game": game_name,
        "score": score,
        "task_id": GAME_IDX[game_name] * 100_000_000 + config_id,
        "seed": seed,
    }
