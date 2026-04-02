from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import numpy as np
import torch

from projects.openspiel_muzero_pt.config_utils import (
    build_model_from_config,
    default_device,
    save_checkpoint,
    load_yaml_config,
)
from projects.openspiel_muzero_pt.pipelines.evaluate_vs_affine_mcts import evaluate_checkpoint
from projects.openspiel_muzero_pt.pipelines.learner import OnlineLearner
from projects.openspiel_muzero_pt.replay.expert_buffer import ExpertBuffer
from projects.openspiel_muzero_pt.utils import JsonProgressWriter, JsonlEventWriter, append_event, eta_seconds, utc_now


def run_warmstart(
    *,
    config_path: str,
    expert_dir: str,
    output_dir: str,
    device: str | None = None,
    seed: int = 0,
) -> dict[str, float | int]:
    config = load_yaml_config(config_path)
    model, adapter = build_model_from_config(config)
    device_obj = default_device(device)
    model.to(device_obj)
    optimizer_cfg = config.get("optimizer", {})
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(optimizer_cfg.get("lr_warmstart", 1.0e-3)),
        weight_decay=float(optimizer_cfg.get("weight_decay", 1.0e-4)),
    )
    learner = OnlineLearner(model=model, adapter=adapter, optimizer=optimizer, device=device_obj)
    expert = ExpertBuffer.from_dir(expert_dir)
    payload = expert.load_all()
    rng = np.random.default_rng(seed)

    total_rows = int(payload["action"].shape[0])
    val_count = max(total_rows // 20, 1)
    indices = np.arange(total_rows)
    rng.shuffle(indices)
    train_index = indices[val_count:]
    val_index = indices[:val_count]
    train_payload = {key: value[train_index] for key, value in payload.items()}
    val_payload = {key: value[val_index] for key, value in payload.items()}

    train_cfg = config.get("train", {})
    batch_size = int(train_cfg.get("batch_size_per_gpu", 512))
    steps = int(train_cfg.get("learner_steps_warmstart", 25000))
    log_interval = int(train_cfg.get("log_interval", max(min(steps // 20, 1000), 1)))
    best_val = float("inf")
    last_metrics = {}
    started_at = time.time()
    output_root = Path(output_dir)
    progress_writer = JsonProgressWriter(output_root / "warmstart.progress.json")
    event_writer = JsonlEventWriter(output_root / "warmstart.events.jsonl")
    progress_payload = {
        "ts": utc_now(),
        "status": "running",
        "phase": "warmstart",
        "step": 0,
        "steps_total": steps,
        "rows_total": total_rows,
        "device": str(device_obj),
        "best_val_score": None,
        "latest_checkpoint": "",
        "estimated_remaining_seconds": None,
    }
    progress_writer.write(progress_payload)
    for step in range(1, steps + 1):
        batch_index = rng.integers(0, train_payload["action"].shape[0], size=batch_size)
        batch = {key: value[batch_index] for key, value in train_payload.items()}
        metrics = learner.train_batch(batch)
        last_metrics = {
            "loss": metrics.loss,
            "policy_loss": metrics.policy_loss,
            "value_loss": metrics.value_loss,
            "reward_loss": metrics.reward_loss,
        }
        if step % max(min(steps // 10, 1000), 1) == 0 or step == steps:
            with torch.no_grad():
                obs = torch.from_numpy(val_payload["obs"]).to(device_obj)
                legal = torch.from_numpy(val_payload["legal_mask"]).to(device_obj)
                policy = torch.from_numpy(val_payload["policy_target"]).to(device_obj)
                values = torch.from_numpy(val_payload["value_target"]).to(device_obj)
                initial = model.initial_inference(obs)
                masked_logits = initial.policy_logits.masked_fill(legal <= 0, -1e9)
                val_policy = -(policy * torch.log_softmax(masked_logits, dim=-1)).sum(dim=-1).mean().item()
                val_value = torch.mean((initial.value - values) ** 2).item()
                val_score = float(val_policy + val_value)
            save_checkpoint(Path(output_dir) / "last.pt", model=model, optimizer=optimizer, step=step, metrics=last_metrics)
            if val_score < best_val:
                best_val = val_score
                save_checkpoint(
                    Path(output_dir) / "best.pt",
                    model=model,
                    optimizer=optimizer,
                    step=step,
                    metrics={**last_metrics, "val_score": val_score},
                )
            progress_payload.update(
                {
                    "ts": utc_now(),
                    "step": step,
                    "loss": metrics.loss,
                    "policy_loss": metrics.policy_loss,
                    "value_loss": metrics.value_loss,
                    "reward_loss": metrics.reward_loss,
                    "val_score": val_score,
                    "best_val_score": best_val,
                    "latest_checkpoint": str(Path(output_dir) / "last.pt"),
                    "estimated_remaining_seconds": eta_seconds(started_at=started_at, completed=step, total=steps),
                }
            )
            progress_writer.write(progress_payload)
            append_event(
                event_writer,
                kind="warmstart_step",
                step=step,
                steps_total=steps,
                loss=metrics.loss,
                val_score=val_score,
                best_val_score=best_val,
            )
        elif step % log_interval == 0:
            progress_payload.update(
                {
                    "ts": utc_now(),
                    "step": step,
                    "loss": metrics.loss,
                    "policy_loss": metrics.policy_loss,
                    "value_loss": metrics.value_loss,
                    "reward_loss": metrics.reward_loss,
                    "best_val_score": best_val,
                    "estimated_remaining_seconds": eta_seconds(started_at=started_at, completed=step, total=steps),
                }
            )
            progress_writer.write(progress_payload)
            append_event(
                event_writer,
                kind="warmstart_log",
                step=step,
                steps_total=steps,
                loss=metrics.loss,
                best_val_score=best_val,
            )
    quick_games = int(config.get("eval", {}).get("quick_gate_games", 50))
    report = evaluate_checkpoint(
        config_path=config_path,
        checkpoint_path=str(Path(output_dir) / "best.pt"),
        games=quick_games,
        device=str(device_obj),
        seed=seed,
        mode="quick",
        num_workers=int(config.get("eval", {}).get("quick_num_workers", 1)),
        output_path=str(output_root / "warmstart.quick_eval.json"),
    )
    report["best_val_score"] = best_val
    report["steps"] = steps
    report["official_ready"] = float(report["win_rate"]) >= float(
        config.get("eval", {}).get("quick_threshold_for_official", config.get("eval", {}).get("acceptance_target_winrate", 0.90))
    )
    progress_payload.update(
        {
            "ts": utc_now(),
            "status": "completed",
            "phase": "warmstart",
            "step": steps,
            "best_val_score": best_val,
            "quick_win_rate": report["win_rate"],
            "official_ready": report["official_ready"],
            "estimated_remaining_seconds": 0.0,
        }
    )
    progress_writer.write(progress_payload)
    append_event(
        event_writer,
        kind="warmstart_complete",
        step=steps,
        quick_win_rate=report["win_rate"],
        official_ready=report["official_ready"],
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Warm-start BoardMuZeroNet from expert labels")
    parser.add_argument("--config", required=True)
    parser.add_argument("--expert", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--device", default="")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    Path(args.out).mkdir(parents=True, exist_ok=True)
    report = run_warmstart(
        config_path=args.config,
        expert_dir=args.expert,
        output_dir=args.out,
        device=args.device or None,
        seed=args.seed,
    )
    report_path = Path(args.out) / "warmstart_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
