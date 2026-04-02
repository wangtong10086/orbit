from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import multiprocessing as mp
import os
from pathlib import Path
import random

import numpy as np

from projects.openspiel_muzero_pt.games.affine_registry import DEFAULT_REGISTRY
from projects.openspiel_muzero_pt.config_utils import load_yaml_config, resolve_spec_from_config
from projects.openspiel_muzero_pt.games.adapters import AffineOpenSpielAdapter, RandomRolloutEvaluator


SUPPORTED_CORPUS_FAMILIES = {"othello"}


def _build_weak_bot(adapter: AffineOpenSpielAdapter, simulations: int, seed: int):
    from open_spiel.python.algorithms import mcts as mcts_lib

    return mcts_lib.MCTSBot(
        game=adapter.build_game(),
        uct_c=1.414,
        max_simulations=max(int(simulations), 1),
        evaluator=RandomRolloutEvaluator(n_rollouts=4, seed=seed),
        random_state=np.random.RandomState(seed + 1),
        solve=True,
    )


def _default_worker_count(requested: int | None, total_items: int) -> int:
    cpu_total = int(os.cpu_count() or 1)
    desired = cpu_total if requested is None or int(requested) <= 0 else int(requested)
    return max(1, min(desired, max(int(total_items), 1)))


def _generate_games_chunk(
    *,
    task_id: int,
    game_indices: list[int],
    weak_mcts_simulations: int,
    seed: int,
) -> dict[int, list[dict[str, object]]]:
    spec = DEFAULT_REGISTRY.get_spec(task_id)
    adapter = AffineOpenSpielAdapter(spec)
    phase_buckets: dict[int, list[dict[str, object]]] = {index: [] for index in range(5)}
    for game_index in game_indices:
        state = adapter.new_initial_state()
        history: list[int] = []
        rng = random.Random(seed + game_index)
        weak_bot = _build_weak_bot(adapter, simulations=weak_mcts_simulations, seed=seed + game_index)
        while not state.is_terminal():
            encoded = adapter.encode_state(state)
            bucket = min(int(encoded.phase * 5.0), 4)
            phase_buckets[bucket].append(
                {
                    "task_id": adapter.spec.task_id,
                    "episode_id": int(game_index),
                    "move_index": encoded.move_index,
                    "phase": encoded.phase,
                    "history_actions": list(history),
                }
            )
            legal = adapter.legal_actions_dense(state)
            if not legal:
                break
            if rng.random() < 0.5:
                action = int(rng.choice(legal))
            else:
                action = adapter.codec.encode_dense(int(weak_bot.step(state)), adapter.spec)
            history.append(action)
            adapter.apply_dense_action(state, action)
    return phase_buckets


def generate_state_corpus(
    *,
    adapter: AffineOpenSpielAdapter,
    output_path: str | Path,
    cheap_games: int,
    sample_states: int,
    weak_mcts_simulations: int,
    seed: int,
    num_workers: int | None = None,
) -> dict[str, int]:
    if adapter.spec.family not in SUPPORTED_CORPUS_FAMILIES:
        supported = ", ".join(sorted(SUPPORTED_CORPUS_FAMILIES))
        raise NotImplementedError(
            f"State corpus builder is currently implemented for: {supported}. "
            f"Requested family={adapter.spec.family}"
        )
    rng = random.Random(seed)
    total_games = int(cheap_games)
    worker_count = _default_worker_count(num_workers, total_games)
    phase_buckets: dict[int, list[dict[str, object]]] = {index: [] for index in range(5)}
    game_ids = list(range(total_games))
    chunks = [chunk.tolist() for chunk in np.array_split(np.asarray(game_ids, dtype=np.int64), worker_count) if len(chunk) > 0]
    if worker_count == 1:
        chunk_results = [
            _generate_games_chunk(
                task_id=adapter.spec.task_id,
                game_indices=chunks[0],
                weak_mcts_simulations=weak_mcts_simulations,
                seed=seed,
            )
        ]
    else:
        with ProcessPoolExecutor(max_workers=worker_count, mp_context=mp.get_context("spawn")) as executor:
            futures = [
                executor.submit(
                    _generate_games_chunk,
                    task_id=adapter.spec.task_id,
                    game_indices=chunk,
                    weak_mcts_simulations=weak_mcts_simulations,
                    seed=seed,
                )
                for chunk in chunks
            ]
            chunk_results = [future.result() for future in futures]
    for chunk_result in chunk_results:
        for bucket, rows in chunk_result.items():
            phase_buckets[int(bucket)].extend(rows)
    per_bucket = max(int(sample_states) // 5, 1)
    kept = []
    for bucket, rows in phase_buckets.items():
        rng.shuffle(rows)
        kept.extend(rows[:per_bucket])
    rng.shuffle(kept)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for row in kept:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"games": total_games, "states": len(kept), "output": str(target)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a cheap Othello state corpus for expert labeling")
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", default="")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--num-workers", type=int, default=0)
    args = parser.parse_args()

    config = load_yaml_config(args.config)
    spec = resolve_spec_from_config(config)
    adapter = AffineOpenSpielAdapter(spec)
    corpus_cfg = config.get("corpus", {})
    output = args.output or f"artifacts/openspiel_muzero_pt/{spec.variant_name}/state_corpus.jsonl"
    summary = generate_state_corpus(
        adapter=adapter,
        output_path=output,
        cheap_games=int(corpus_cfg.get("cheap_games", 2000)),
        sample_states=int(corpus_cfg.get("sample_states", 120000)),
        weak_mcts_simulations=int(corpus_cfg.get("weak_mcts_simulations", 16)),
        seed=int(args.seed),
        num_workers=int(args.num_workers) if args.num_workers > 0 else int(corpus_cfg.get("num_workers", 0) or 0),
    )
    print(json.dumps({"output": output, **summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
