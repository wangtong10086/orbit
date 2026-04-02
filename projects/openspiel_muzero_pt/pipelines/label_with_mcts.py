from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import multiprocessing as mp
import os
from pathlib import Path

import numpy as np

from projects.openspiel_muzero_pt.games.affine_registry import DEFAULT_REGISTRY
from projects.openspiel_muzero_pt.config_utils import load_yaml_config, resolve_spec_from_config
from projects.openspiel_muzero_pt.games.adapters import AffineOpenSpielAdapter, RandomRolloutEvaluator
from projects.openspiel_muzero_pt.replay.expert_buffer import ReplaySample, pack_samples


def rollout_mcts_policy(
    state,
    *,
    adapter: AffineOpenSpielAdapter,
    simulations: int,
    rollouts: int,
    seed: int,
) -> tuple[np.ndarray, float]:
    if state.is_terminal():
        policy = np.zeros((adapter.spec.action_dim,), dtype=np.float32)
        return policy, 0.0
    root_player = int(state.current_player())
    legal = adapter.legal_actions_dense(state)
    evaluator = RandomRolloutEvaluator(n_rollouts=rollouts, seed=seed)
    visit_counts = np.zeros((adapter.spec.action_dim,), dtype=np.float32)
    value_sums = np.zeros((adapter.spec.action_dim,), dtype=np.float32)
    for _ in range(int(simulations)):
        action = int(legal[(seed + int(visit_counts.sum())) % len(legal)]) if legal else 0
        best_score = None
        total_visits = float(max(visit_counts.sum(), 1.0))
        priors = np.full((adapter.spec.action_dim,), 0.0, dtype=np.float32)
        priors[legal] = 1.0 / float(len(legal))
        for candidate in legal:
            q = value_sums[candidate] / visit_counts[candidate] if visit_counts[candidate] > 0 else 0.0
            score = q + 1.5 * priors[candidate] * np.sqrt(total_visits) / (1.0 + visit_counts[candidate])
            if best_score is None or score > best_score:
                best_score = score
                action = int(candidate)
        working = state.clone()
        adapter.apply_dense_action(working, action)
        if working.is_terminal():
            value = float(working.returns()[root_player])
        else:
            value = float(evaluator.evaluate(working)[root_player])
        visit_counts[action] += 1.0
        value_sums[action] += value
    if visit_counts.sum() <= 0:
        policy = np.zeros((adapter.spec.action_dim,), dtype=np.float32)
        policy[legal] = 1.0 / float(len(legal))
        return policy, 0.0
    policy = visit_counts / float(visit_counts.sum())
    action_values = np.zeros((adapter.spec.action_dim,), dtype=np.float32)
    positive = visit_counts > 0
    action_values[positive] = value_sums[positive] / visit_counts[positive]
    value = float(np.sum(policy * action_values))
    return policy.astype(np.float32), float(value)


def label_corpus(
    *,
    adapter: AffineOpenSpielAdapter,
    corpus_path: str | Path,
    output_dir: str | Path,
    label_simulations: int,
    label_rollouts: int,
    strong_simulation_scale: int,
    strong_fraction: float,
    seed: int,
    num_workers: int | None = None,
) -> dict[str, int]:
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    for stale in output_root.glob("expert_*.npz"):
        stale.unlink()
    for stale in output_root.glob("expert_*.json"):
        stale.unlink()
    with Path(corpus_path).open("r", encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle]
    worker_count = _default_worker_count(num_workers, len(records))
    chunks = [chunk.tolist() for chunk in np.array_split(np.arange(len(records), dtype=np.int64), worker_count) if len(chunk) > 0]
    if worker_count == 1:
        counts = [
            _label_records_chunk(
                task_id=adapter.spec.task_id,
                records=[records[index] for index in chunks[0]],
                output_dir=str(output_root),
                shard_index=0,
                label_simulations=label_simulations,
                label_rollouts=label_rollouts,
                strong_simulation_scale=strong_simulation_scale,
                strong_fraction=strong_fraction,
                seed=seed,
            )
        ]
    else:
        with ProcessPoolExecutor(max_workers=worker_count, mp_context=mp.get_context("spawn")) as executor:
            futures = [
                executor.submit(
                    _label_records_chunk,
                    task_id=adapter.spec.task_id,
                    records=[records[index] for index in chunk],
                    output_dir=str(output_root),
                    shard_index=chunk_index,
                    label_simulations=label_simulations,
                    label_rollouts=label_rollouts,
                    strong_simulation_scale=strong_simulation_scale,
                    strong_fraction=strong_fraction,
                    seed=seed + (chunk_index * 1_000_000),
                )
                for chunk_index, chunk in enumerate(chunks)
            ]
            counts = [future.result() for future in futures]
    return {"labeled_states": int(sum(counts))}


def _default_worker_count(requested: int | None, total_items: int) -> int:
    cpu_total = int(os.cpu_count() or 1)
    desired = cpu_total if requested is None or int(requested) <= 0 else int(requested)
    return max(1, min(desired, max(int(total_items), 1)))


def _label_records_chunk(
    *,
    task_id: int,
    records: list[dict[str, object]],
    output_dir: str,
    shard_index: int,
    label_simulations: int,
    label_rollouts: int,
    strong_simulation_scale: int,
    strong_fraction: float,
    seed: int,
) -> int:
    spec = DEFAULT_REGISTRY.get_spec(task_id)
    adapter = AffineOpenSpielAdapter(spec)
    rng = np.random.default_rng(seed)
    samples: list[ReplaySample] = []
    total = 0
    for record in records:
        state = adapter.clone_from_history([int(action) for action in record["history_actions"]])
        encoded = adapter.encode_state(state)
        if encoded.terminal:
            continue
        stronger = rng.random() < float(strong_fraction)
        simulations = int(label_simulations) * (int(strong_simulation_scale) if stronger else 1)
        policy_target, value_target = rollout_mcts_policy(
            state,
            adapter=adapter,
            simulations=simulations,
            rollouts=int(label_rollouts),
            seed=seed + total,
        )
        action = int(np.argmax(policy_target))
        next_state = state.clone()
        adapter.apply_dense_action(next_state, action)
        next_encoded = adapter.encode_state(next_state)
        if next_encoded.terminal:
            next_policy_target = np.zeros((adapter.spec.action_dim,), dtype=np.float32)
            next_value_target = 0.0
            recurrent_mask = 0.0
        else:
            next_policy_target, next_value_target = rollout_mcts_policy(
                next_state,
                adapter=adapter,
                simulations=simulations,
                rollouts=int(label_rollouts),
                seed=seed + total + 10_000_000,
            )
            recurrent_mask = 1.0
        reward_target = adapter.current_player_reward(state, next_state, encoded.current_player)
        samples.append(
            ReplaySample(
                obs=encoded.obs,
                legal_mask=encoded.legal_mask,
                action=action,
                next_obs=next_encoded.obs,
                next_legal_mask=next_encoded.legal_mask,
                next_policy_target=next_policy_target,
                next_value_target=float(next_value_target),
                recurrent_mask=recurrent_mask,
                policy_target=policy_target,
                value_target=float(value_target),
                reward_target=float(reward_target),
                phase=encoded.phase,
                move_index=encoded.move_index,
                variant_id=adapter.spec.variant_index,
                weight_version=0,
            )
        )
        total += 1
    if samples:
        shard_path = Path(output_dir) / f"expert_{int(shard_index):06d}.npz"
        np.savez_compressed(shard_path, **pack_samples(samples))
        shard_path.with_suffix(".json").write_text(json.dumps({"rows": len(samples)}, indent=2), encoding="utf-8")
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Label a cheap Othello state corpus with rollout MCTS")
    parser.add_argument("--config", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--num-workers", type=int, default=0)
    args = parser.parse_args()

    config = load_yaml_config(args.config)
    spec = resolve_spec_from_config(config)
    adapter = AffineOpenSpielAdapter(spec)
    expert_cfg = config.get("expert", {})
    summary = label_corpus(
        adapter=adapter,
        corpus_path=args.input,
        output_dir=args.output,
        label_simulations=int(expert_cfg.get("label_simulations", adapter.spec.baseline_max_simulations)),
        label_rollouts=int(expert_cfg.get("label_rollouts", adapter.spec.baseline_n_rollouts)),
        strong_simulation_scale=int(expert_cfg.get("strong_simulation_scale", 2)),
        strong_fraction=float(expert_cfg.get("strong_fraction", 0.2)),
        seed=args.seed,
        num_workers=int(args.num_workers) if args.num_workers > 0 else int(expert_cfg.get("num_workers", 0) or 0),
    )
    print(json.dumps({"output": args.output, **summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
