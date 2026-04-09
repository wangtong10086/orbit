from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch

from projects.openspiel_muzero_pt.config_utils import (
    build_model_from_config,
    build_search_engine,
    default_device,
    load_checkpoint,
    load_yaml_config,
)
from projects.openspiel_muzero_pt.pipelines.selfplay_actor import generate_selfplay_games, pack_selfplay_games


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export MuZero self-play trajectories from a checkpoint")
    parser.add_argument("--config", required=True, help="Training config YAML")
    parser.add_argument("--checkpoint", required=True, help="Model checkpoint path")
    parser.add_argument("--output-dir", required=True, help="Directory to write exported trajectories")
    parser.add_argument("--games", type=int, default=256, help="Number of self-play games to generate")
    parser.add_argument("--parallel-games", type=int, default=16, help="Number of concurrent games")
    parser.add_argument("--seed", type=int, default=0, help="Random seed")
    parser.add_argument("--device", default="", help="Torch device override")
    parser.add_argument(
        "--mode",
        choices=("train", "eval"),
        default="train",
        help="Search budget mode used for self-play export",
    )
    return parser.parse_args()


def _game_record(game) -> dict[str, object]:
    return {
        "episode_id": int(game.episode_id),
        "positions": int(len(game.samples)),
        "outcome": float(game.outcome),
        "mean_search_ms": float(game.mean_search_ms),
        "moves": [
            {
                "move_index": int(sample.move_index),
                "action": int(sample.action),
                "value_target": float(sample.value_target),
                "reward_target": float(sample.reward_target),
                "recurrent_mask": float(sample.recurrent_mask),
            }
            for sample in game.samples
        ],
    }


def main() -> None:
    args = _parse_args()
    config = load_yaml_config(args.config)
    model, adapter = build_model_from_config(config)
    device = default_device(args.device or None)
    model.to(device)
    model.eval()
    load_checkpoint(args.checkpoint, model=model)
    search_overrides = None
    if args.mode == "eval":
        search_cfg = dict(config.get("search", {}))
        search_overrides = {
            "train_num_simulations": int(search_cfg.get("eval_num_simulations", search_cfg.get("train_num_simulations", 64))),
            "reanalyse_num_simulations": int(search_cfg.get("eval_num_simulations", search_cfg.get("reanalyse_num_simulations", 128))),
        }
    search = build_search_engine(
        model=model,
        adapter=adapter,
        config=config,
        device=device,
        seed=int(args.seed),
        search_overrides=search_overrides,
    )

    games = generate_selfplay_games(
        adapter=adapter,
        search_engine=search,
        num_games=int(args.games),
        seed=int(args.seed),
        num_parallel_games=int(args.parallel_games),
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    packed = pack_selfplay_games(games)
    payload = packed["payload"]
    np.savez_compressed(output_dir / "samples.npz", **payload)
    (output_dir / "summary.json").write_text(
        json.dumps(
            {
                "config": args.config,
                "checkpoint": args.checkpoint,
                "games": int(packed["games_generated"]),
                "positions": int(packed["positions_generated"]),
                "mean_search_ms": float(packed["mean_search_ms"]),
                "mean_game_len": float(packed["mean_game_len"]),
                "device": str(device),
                "mode": args.mode,
                "seed": int(args.seed),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    with (output_dir / "games.jsonl").open("w", encoding="utf-8") as handle:
        for game in games:
            handle.write(json.dumps(_game_record(game), ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
