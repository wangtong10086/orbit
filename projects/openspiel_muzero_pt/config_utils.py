from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import torch
import yaml

from .games.adapters import AffineOpenSpielAdapter
from .games.affine_registry import DEFAULT_REGISTRY
from .model.board_muzero import BoardMuZeroConfig, BoardMuZeroNet
from .runtime.inference import LocalModelInferenceClient, ModelInferenceClient
from .search.batched_search import SearchConfig, SearchEngine


def load_yaml_config(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def resolve_spec_from_config(config: dict[str, Any]):
    task_ids = config.get("game", {}).get("task_ids", [])
    if not task_ids:
        raise ValueError("Config must define game.task_ids")
    return DEFAULT_REGISTRY.get_spec(int(task_ids[0]))


def build_model_from_config(config: dict[str, Any]) -> tuple[BoardMuZeroNet, AffineOpenSpielAdapter]:
    spec = resolve_spec_from_config(config)
    adapter = AffineOpenSpielAdapter(spec)
    model_cfg = config.get("model", {})
    model = BoardMuZeroNet(
        BoardMuZeroConfig(
            input_channels=spec.input_channels,
            board_height=spec.pad_h,
            board_width=spec.pad_w,
            action_dim=spec.action_dim,
            channels=int(model_cfg.get("channels", 128)),
            repr_blocks=int(model_cfg.get("repr_blocks", 10)),
            dyn_blocks=int(model_cfg.get("dyn_blocks", 4)),
            head_hidden=int(model_cfg.get("head_hidden", 256)),
        )
    )
    return model, adapter


def build_search_engine(
    *,
    model: BoardMuZeroNet | None,
    adapter: AffineOpenSpielAdapter,
    config: dict[str, Any],
    device: torch.device | str,
    seed: int = 0,
    search_overrides: dict[str, Any] | None = None,
    inference_client: ModelInferenceClient | None = None,
) -> SearchEngine:
    search_cfg = dict(config.get("search", {}))
    if search_overrides:
        search_cfg.update(search_overrides)
    if inference_client is None:
        if model is None:
            raise ValueError("Either model or inference_client must be provided")
        inference_client = LocalModelInferenceClient(model=model, device=device)
    return SearchEngine(
        inference_client=inference_client,
        adapter=adapter,
        config=SearchConfig(
            train_num_simulations=int(search_cfg.get("train_num_simulations", 64)),
            reanalyse_num_simulations=int(search_cfg.get("reanalyse_num_simulations", 128)),
            eval_num_simulations=int(search_cfg.get("eval_num_simulations", 128)),
            c_puct=float(search_cfg.get("c_puct", 1.5)),
            root_dirichlet_epsilon=float(search_cfg.get("root_dirichlet_epsilon", 0.25)),
            max_num_considered_actions=int(search_cfg.get("max_num_considered_actions", 32)),
            seed=seed,
        ),
        device=device,
    )


def clone_config(config: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(config)


def default_device(requested: str | None = None) -> torch.device:
    if requested:
        return torch.device(requested)
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def save_checkpoint(
    path: str | Path,
    *,
    model: BoardMuZeroNet,
    optimizer: torch.optim.Optimizer | None = None,
    step: int = 0,
    metrics: dict[str, float] | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    payload = {
        "model_state": model.state_dict(),
        "step": int(step),
        "metrics": dict(metrics or {}),
        "extra": dict(extra or {}),
    }
    if optimizer is not None:
        payload["optimizer_state"] = optimizer.state_dict()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    torch.save(payload, target)


def load_checkpoint(path: str | Path, *, model: BoardMuZeroNet, optimizer: torch.optim.Optimizer | None = None) -> dict[str, Any]:
    payload = torch.load(Path(path), map_location="cpu")
    model.load_state_dict(payload["model_state"])
    if optimizer is not None and "optimizer_state" in payload:
        optimizer.load_state_dict(payload["optimizer_state"])
    return payload
