from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import time

import numpy as np
import torch

from projects.openspiel_muzero_pt.config_utils import (
    build_model_from_config,
    build_search_engine,
    clone_config,
    default_device,
    load_checkpoint,
    load_yaml_config,
    resolve_spec_from_config,
)
from projects.openspiel_muzero_pt.games.adapters import AffineOpenSpielAdapter
from projects.openspiel_muzero_pt.pipelines.evaluate_vs_affine_mcts import _resolve_eval_mode_settings


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export model-vs-MCTS winning samples")
    parser.add_argument("--config", required=True, help="Training config YAML")
    parser.add_argument("--checkpoint", required=True, help="Model checkpoint path")
    parser.add_argument("--output-dir", required=True, help="Directory for exported wins")
    parser.add_argument("--mode", choices=("quick", "official"), default="quick", help="Evaluation budget preset")
    parser.add_argument("--target-wins", type=int, default=5000, help="Stop after collecting this many winning games")
    parser.add_argument("--max-games", type=int, default=30000, help="Maximum games to play")
    parser.add_argument("--num-workers", type=int, default=32, help="Concurrent game workers")
    parser.add_argument("--shard-size", type=int, default=4096, help="Rows per output shard")
    parser.add_argument("--seed", type=int, default=0, help="Random seed")
    parser.add_argument("--device", default="", help="Torch device override")
    return parser.parse_args()


def _baseline_step(context: dict[str, object], adapter: AffineOpenSpielAdapter) -> tuple[int, int]:
    action = int(context["baseline"].step(context["state"].clone()))
    return int(context["game_index"]), adapter.codec.encode_dense(action, adapter.spec)


def _pack_agent_samples(rows: list[dict[str, object]]) -> dict[str, np.ndarray]:
    return {
        "obs": np.stack([np.asarray(row["obs"], dtype=np.float32) for row in rows]).astype(np.float32),
        "legal_mask": np.stack([np.asarray(row["legal_mask"], dtype=np.float32) for row in rows]).astype(np.float32),
        "policy_target": np.stack([np.asarray(row["policy_target"], dtype=np.float32) for row in rows]).astype(np.float32),
        "action": np.asarray([int(row["action"]) for row in rows], dtype=np.int64),
        "phase": np.asarray([float(row["phase"]) for row in rows], dtype=np.float32),
        "move_index": np.asarray([int(row["move_index"]) for row in rows], dtype=np.int64),
        "variant_id": np.asarray([int(row["variant_id"]) for row in rows], dtype=np.int64),
        "agent_player": np.asarray([int(row["agent_player"]) for row in rows], dtype=np.int64),
        "game_index": np.asarray([int(row["game_index"]) for row in rows], dtype=np.int64),
        "outcome": np.asarray([float(row["outcome"]) for row in rows], dtype=np.float32),
    }


class SampleShardWriter:
    def __init__(self, output_dir: Path, *, shard_size: int):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.shard_size = max(int(shard_size), 1)
        self._buffer: list[dict[str, object]] = []
        self._shard_index = 0
        self.total_rows = 0

    def add_rows(self, rows: list[dict[str, object]]) -> None:
        if not rows:
            return
        self._buffer.extend(rows)
        while len(self._buffer) >= self.shard_size:
            chunk = self._buffer[: self.shard_size]
            del self._buffer[: self.shard_size]
            self._flush_chunk(chunk)

    def flush(self) -> None:
        if self._buffer:
            chunk = list(self._buffer)
            self._buffer.clear()
            self._flush_chunk(chunk)

    def _flush_chunk(self, rows: list[dict[str, object]]) -> None:
        payload = _pack_agent_samples(rows)
        shard_path = self.output_dir / f"winning_agent_samples_{self._shard_index:06d}.npz"
        np.savez_compressed(shard_path, **payload)
        meta = {
            "rows": int(payload["action"].shape[0]),
            "shard_index": int(self._shard_index),
        }
        shard_path.with_suffix(".json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        self.total_rows += int(payload["action"].shape[0])
        self._shard_index += 1


def main() -> None:
    args = _parse_args()
    config = load_yaml_config(args.config)
    spec = resolve_spec_from_config(config)
    settings = _resolve_eval_mode_settings(config, spec=spec, mode=args.mode)
    model, adapter = build_model_from_config(config)
    device = default_device(args.device or None)
    model.to(device)
    load_checkpoint(args.checkpoint, model=model)
    model.eval()

    search_config = clone_config(config)
    search_config.setdefault("search", {})
    search_config["search"] = dict(search_config.get("search", {}))
    search_config["search"]["eval_num_simulations"] = settings.agent_simulations
    search = build_search_engine(
        model=model,
        adapter=adapter,
        config=search_config,
        device=device,
        seed=int(args.seed),
        search_overrides={"eval_num_simulations": settings.agent_simulations},
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    wins_path = output_dir / "winning_games.jsonl"
    samples_dir = output_dir / "winning_agent_samples"
    summary_path = output_dir / "summary.json"
    shard_writer = SampleShardWriter(samples_dir, shard_size=int(args.shard_size))

    summary = {
        "config": args.config,
        "checkpoint": args.checkpoint,
        "mode": args.mode,
        "target_wins": int(args.target_wins),
        "max_games": int(args.max_games),
        "num_workers": int(args.num_workers),
        "shard_size": int(args.shard_size),
        "seed": int(args.seed),
        "games_played": 0,
        "wins_kept": 0,
        "losses": 0,
        "draws": 0,
        "agent_samples": 0,
        "avg_game_seconds": 0.0,
        "device": str(device),
    }

    def _spawn_one(game_index: int) -> dict[str, object]:
        return {
            "game_index": int(game_index),
            "agent_player": int(game_index % 2),
            "state": adapter.new_initial_state(),
            "baseline": adapter.create_affine_mcts_bot(
                seed=int(args.seed) + game_index,
                simulations=settings.baseline_simulations,
                rollouts=settings.baseline_rollouts,
            ),
            "recorded_agent_moves": [],
            "move_count": 0,
            "started_at": time.time(),
        }

    with wins_path.open("w", encoding="utf-8") as wins_handle:
        pending_game_index = 0
        active: list[dict[str, object]] = []
        finished_durations: list[float] = []

        while pending_game_index < int(args.max_games) and len(active) < int(args.num_workers):
            active.append(_spawn_one(pending_game_index))
            pending_game_index += 1

        with ThreadPoolExecutor(max_workers=max(int(args.num_workers), 1)) as executor:
            while active and int(summary["wins_kept"]) < int(args.target_wins):
                agent_games = [
                    ctx for ctx in active if not ctx["state"].is_terminal() and int(ctx["state"].current_player()) == int(ctx["agent_player"])
                ]
                if agent_games:
                    encoded_batch = [adapter.encode_state(ctx["state"]) for ctx in agent_games]
                    obs_batch = torch.from_numpy(np.stack([encoded.obs for encoded in encoded_batch]).astype(np.float32)).to(device)
                    legal_batch = torch.from_numpy(np.stack([encoded.legal_mask for encoded in encoded_batch]).astype(np.float32)).to(device)
                    result = search.run(
                        obs_batch,
                        legal_batch,
                        [ctx["state"] for ctx in agent_games],
                        mode="eval",
                        encoded_state_batch=encoded_batch,
                    )
                    for index, ctx in enumerate(agent_games):
                        encoded = encoded_batch[index]
                        action = int(result.chosen_action[index])
                        ctx["recorded_agent_moves"].append(
                            {
                                "obs": encoded.obs.copy(),
                                "legal_mask": encoded.legal_mask.copy(),
                                "policy_target": result.root_policy[index].copy(),
                                "action": action,
                                "phase": float(encoded.phase),
                                "move_index": int(encoded.move_index),
                                "variant_id": int(adapter.spec.variant_index),
                                "agent_player": int(ctx["agent_player"]),
                                "game_index": int(ctx["game_index"]),
                            }
                        )
                        adapter.apply_dense_action(ctx["state"], action)
                        ctx["move_count"] = int(ctx["move_count"]) + 1

                baseline_games = [
                    ctx for ctx in active if not ctx["state"].is_terminal() and int(ctx["state"].current_player()) != int(ctx["agent_player"])
                ]
                if baseline_games:
                    futures = [executor.submit(_baseline_step, ctx, adapter) for ctx in baseline_games]
                    action_by_game = dict(f.result() for f in futures)
                    for ctx in baseline_games:
                        adapter.apply_dense_action(ctx["state"], int(action_by_game[int(ctx["game_index"])]))
                        ctx["move_count"] = int(ctx["move_count"]) + 1

                for ctx in list(active):
                    if not ctx["state"].is_terminal():
                        continue
                    summary["games_played"] = int(summary["games_played"]) + 1
                    finished_durations.append(time.time() - float(ctx["started_at"]))
                    summary["avg_game_seconds"] = float(np.mean(finished_durations))
                    outcome = float(ctx["state"].returns()[int(ctx["agent_player"])])
                    if outcome > 0:
                        summary["wins_kept"] = int(summary["wins_kept"]) + 1
                        winning_rows: list[dict[str, object]] = []
                        for row in ctx["recorded_agent_moves"]:
                            row["outcome"] = outcome
                            winning_rows.append(row)
                        shard_writer.add_rows(winning_rows)
                        summary["agent_samples"] = int(shard_writer.total_rows)
                        wins_handle.write(
                            json.dumps(
                                {
                                    "game_index": int(ctx["game_index"]),
                                    "agent_player": int(ctx["agent_player"]),
                                    "result": "win",
                                    "outcome": outcome,
                                    "moves": int(ctx["move_count"]),
                                    "agent_move_count": len(ctx["recorded_agent_moves"]),
                                    "actions": [int(row["action"]) for row in ctx["recorded_agent_moves"]],
                                    "agent_samples_total": int(summary["agent_samples"]),
                                },
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
                        wins_handle.flush()
                    elif outcome < 0:
                        summary["losses"] = int(summary["losses"]) + 1
                    else:
                        summary["draws"] = int(summary["draws"]) + 1

                    active.remove(ctx)
                    if pending_game_index < int(args.max_games) and int(summary["wins_kept"]) < int(args.target_wins):
                        active.append(_spawn_one(pending_game_index))
                        pending_game_index += 1

    if int(summary["wins_kept"]) <= 0:
        raise RuntimeError("No winning games were collected; nothing to export")
    shard_writer.flush()
    summary["agent_samples"] = int(shard_writer.total_rows)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
