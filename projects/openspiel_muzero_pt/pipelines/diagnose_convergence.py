from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from projects.openspiel_muzero_pt.config_utils import load_yaml_config, resolve_spec_from_config
from projects.openspiel_muzero_pt.games.adapters import AffineOpenSpielAdapter
from projects.openspiel_muzero_pt.pipelines.label_with_mcts import rollout_mcts_policy
from projects.openspiel_muzero_pt.replay.expert_buffer import ExpertBuffer


def _policy_entropy(policy: np.ndarray) -> float:
    policy = np.asarray(policy, dtype=np.float32)
    clipped = np.clip(policy, 1.0e-8, None)
    return float(-(policy * np.log(clipped)).sum())


def _budget_summary(config: dict[str, object]) -> dict[str, object]:
    search_cfg = dict(config.get("search", {}))
    expert_cfg = dict(config.get("expert", {}))
    eval_cfg = dict(config.get("eval", {}))
    return {
        "train_num_simulations": int(search_cfg.get("train_num_simulations", 0)),
        "reanalyse_num_simulations": int(search_cfg.get("reanalyse_num_simulations", 0)),
        "eval_num_simulations": int(search_cfg.get("eval_num_simulations", 0)),
        "teacher_label_simulations": int(expert_cfg.get("label_simulations", 0)),
        "teacher_label_rollouts": int(expert_cfg.get("label_rollouts", 0)),
        "quick_agent_simulations": int(eval_cfg.get("quick_agent_simulations", 0)),
        "quick_baseline_simulations": int(eval_cfg.get("quick_baseline_simulations", 0)),
        "quick_baseline_rollouts": int(eval_cfg.get("quick_baseline_rollouts", 0)),
        "official_agent_simulations": int(eval_cfg.get("official_agent_simulations", 0)),
        "official_baseline_simulations": int(eval_cfg.get("official_baseline_simulations", 0)),
        "official_baseline_rollouts": int(eval_cfg.get("official_baseline_rollouts", 0)),
    }


def _teacher_audit(
    *,
    corpus_path: str,
    adapter: AffineOpenSpielAdapter,
    current_simulations: int,
    current_rollouts: int,
    strong_simulations: int,
    strong_rollouts: int,
    sample_states: int,
) -> dict[str, object]:
    with Path(corpus_path).open("r", encoding="utf-8") as handle:
        records = [json.loads(line) for _, line in zip(range(max(int(sample_states), 1)), handle)]
    current_entropies: list[float] = []
    strong_entropies: list[float] = []
    current_values: list[float] = []
    strong_values: list[float] = []
    legal_counts: list[int] = []
    agreement = 0
    samples: list[dict[str, object]] = []
    for index, record in enumerate(records):
        state = adapter.clone_from_history([int(action) for action in record["history_actions"]])
        current_policy, current_value = rollout_mcts_policy(
            state,
            adapter=adapter,
            simulations=int(current_simulations),
            rollouts=int(current_rollouts),
            seed=1_000 + index,
        )
        strong_policy, strong_value = rollout_mcts_policy(
            state,
            adapter=adapter,
            simulations=int(strong_simulations),
            rollouts=int(strong_rollouts),
            seed=10_000 + index,
        )
        current_action = int(np.argmax(current_policy))
        strong_action = int(np.argmax(strong_policy))
        agreement += int(current_action == strong_action)
        current_entropies.append(_policy_entropy(current_policy))
        strong_entropies.append(_policy_entropy(strong_policy))
        current_values.append(float(current_value))
        strong_values.append(float(strong_value))
        legal_counts.append(int((adapter.encode_state(state).legal_mask > 0).sum()))
        if len(samples) < 8:
            samples.append(
                {
                    "index": index,
                    "current_action": current_action,
                    "strong_action": strong_action,
                    "current_entropy": current_entropies[-1],
                    "strong_entropy": strong_entropies[-1],
                    "current_value": float(current_value),
                    "strong_value": float(strong_value),
                }
            )
    return {
        "states_evaluated": len(records),
        "current_policy_entropy_mean": float(np.mean(current_entropies)) if current_entropies else 0.0,
        "strong_policy_entropy_mean": float(np.mean(strong_entropies)) if strong_entropies else 0.0,
        "current_value_mean": float(np.mean(current_values)) if current_values else 0.0,
        "strong_value_mean": float(np.mean(strong_values)) if strong_values else 0.0,
        "chosen_action_agreement": float(agreement / max(len(records), 1)),
        "legal_count_mean": float(np.mean(legal_counts)) if legal_counts else 0.0,
        "samples": samples,
    }


def _sample_payload_rows(payload: dict[str, np.ndarray], *, sample_rows: int) -> dict[str, object]:
    rows = min(int(sample_rows), int(payload["action"].shape[0]))
    legal_count = np.asarray(payload["legal_mask"], dtype=np.float32).sum(axis=1)
    entropy = np.asarray([_policy_entropy(row) for row in payload["policy_target"]], dtype=np.float32)
    sample = []
    for index in range(rows):
        sample.append(
            {
                "row_index": int(index),
                "policy_entropy": float(entropy[index]),
                "value_target": float(payload["value_target"][index]),
                "reward_target": float(payload["reward_target"][index]),
                "legal_count": int(legal_count[index]),
                "chosen_action": int(payload["action"][index]),
            }
        )
    return {
        "rows_total": int(payload["action"].shape[0]),
        "policy_entropy_mean": float(entropy.mean()) if entropy.size else 0.0,
        "value_target_mean": float(np.asarray(payload["value_target"], dtype=np.float32).mean()) if rows else 0.0,
        "reward_target_mean": float(np.asarray(payload["reward_target"], dtype=np.float32).mean()) if rows else 0.0,
        "legal_count_mean": float(legal_count.mean()) if legal_count.size else 0.0,
        "sample_rows": sample,
    }


def _events_audit(events_path: str) -> dict[str, object]:
    latest_train = None
    latest_batch_diag = None
    latest_heartbeats: dict[int, dict[str, object]] = {}
    train_window: list[dict[str, object]] = []
    with Path(events_path).open("r", encoding="utf-8") as handle:
        for line in handle:
            event = json.loads(line)
            kind = str(event.get("kind", ""))
            if kind == "train_log":
                latest_train = event
                train_window.append(event)
                if len(train_window) > 50:
                    train_window.pop(0)
            elif kind == "batch_diagnostics":
                latest_batch_diag = event
            elif kind == "actor_heartbeat":
                latest_heartbeats[int(event["worker_id"])] = event
    starvation_suspected = False
    if train_window and latest_heartbeats:
        replay_values = {int(item.get("replay_rows", -1)) for item in train_window}
        game_values = {int(item.get("selfplay_games_completed", -1)) for item in train_window}
        pending_rows = sum(int(event.get("pending_rows_in_active_slots", 0)) for event in latest_heartbeats.values())
        starvation_suspected = len(replay_values) <= 1 and len(game_values) <= 1 and pending_rows > 0
    return {
        "latest_train_log": latest_train,
        "latest_batch_diagnostics": latest_batch_diag,
        "latest_actor_heartbeats": latest_heartbeats,
        "starvation_suspected": starvation_suspected,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose MuZero convergence failures from configs, teacher labels, and online events")
    parser.add_argument("--config", required=True)
    parser.add_argument("--corpus", default="")
    parser.add_argument("--expert", default="")
    parser.add_argument("--online-events", default="")
    parser.add_argument("--quick-eval", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--teacher-states", type=int, default=32)
    parser.add_argument("--teacher-strong-simulations", type=int, default=0)
    parser.add_argument("--teacher-strong-rollouts", type=int, default=0)
    parser.add_argument("--sample-rows", type=int, default=8)
    args = parser.parse_args()

    config = load_yaml_config(args.config)
    spec = resolve_spec_from_config(config)
    adapter = AffineOpenSpielAdapter(spec)
    report: dict[str, object] = {
        "config": args.config,
        "variant": spec.variant_name,
        "budget_summary": _budget_summary(config),
    }

    if args.quick_eval and Path(args.quick_eval).exists():
        report["quick_eval"] = json.loads(Path(args.quick_eval).read_text(encoding="utf-8"))

    if args.corpus:
        expert_cfg = dict(config.get("expert", {}))
        current_simulations = int(expert_cfg.get("label_simulations", spec.baseline_max_simulations))
        current_rollouts = int(expert_cfg.get("label_rollouts", spec.baseline_n_rollouts))
        strong_simulations = int(args.teacher_strong_simulations or max(current_simulations * 4, current_simulations))
        strong_rollouts = int(args.teacher_strong_rollouts or max(current_rollouts * 2, current_rollouts))
        report["teacher_audit"] = _teacher_audit(
            corpus_path=args.corpus,
            adapter=adapter,
            current_simulations=current_simulations,
            current_rollouts=current_rollouts,
            strong_simulations=strong_simulations,
            strong_rollouts=strong_rollouts,
            sample_states=args.teacher_states,
        )

    if args.expert:
        payload = ExpertBuffer.from_dir(args.expert).load_all()
        report["expert_target_audit"] = _sample_payload_rows(payload, sample_rows=args.sample_rows)

    if args.online_events and Path(args.online_events).exists():
        report["online_events_audit"] = _events_audit(args.online_events)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
