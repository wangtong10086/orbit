from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
from pathlib import Path
import random
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
from projects.openspiel_muzero_pt.utils import JsonProgressWriter, JsonlEventWriter, append_event, eta_seconds, utc_now


@dataclass(frozen=True, slots=True)
class EvalModeSettings:
    mode: str
    games: int
    num_workers: int
    agent_simulations: int
    baseline_simulations: int
    baseline_rollouts: int
    quick_threshold_for_official: float


@dataclass(slots=True)
class EvalGameContext:
    game_index: int
    agent_player: int
    state: object
    baseline: object
    move_count: int = 0


def _resolve_eval_mode_settings(
    config: dict[str, object],
    *,
    spec,
    mode: str,
    games_override: int | None = None,
    num_workers_override: int | None = None,
) -> EvalModeSettings:
    eval_cfg = dict(config.get("eval", {}))
    search_cfg = dict(config.get("search", {}))
    cpu_default = max(1, os_cpu_count())
    quick_games = int(eval_cfg.get("quick_games", eval_cfg.get("quick_gate_games", 200)))
    official_games = int(eval_cfg.get("official_games", 1000))
    quick_workers = int(eval_cfg.get("quick_num_workers", 0) or 0)
    official_workers = int(eval_cfg.get("official_num_workers", 0) or 0)
    if quick_workers <= 0:
        quick_workers = cpu_default
    if official_workers <= 0:
        official_workers = cpu_default
    quick_agent_simulations = int(
        eval_cfg.get(
            "quick_agent_simulations",
            min(int(search_cfg.get("eval_num_simulations", 128)), max(32, int(search_cfg.get("train_num_simulations", 64)))),
        )
    )
    official_agent_simulations = int(eval_cfg.get("official_agent_simulations", search_cfg.get("eval_num_simulations", 128)))
    quick_baseline_simulations = int(
        eval_cfg.get(
            "quick_baseline_simulations",
            min(spec.baseline_max_simulations, max(64, quick_agent_simulations)),
        )
    )
    quick_baseline_rollouts = int(eval_cfg.get("quick_baseline_rollouts", min(spec.baseline_n_rollouts, 4)))
    official_baseline_simulations = int(eval_cfg.get("official_baseline_simulations", spec.baseline_max_simulations))
    official_baseline_rollouts = int(eval_cfg.get("official_baseline_rollouts", spec.baseline_n_rollouts))
    threshold = float(eval_cfg.get("quick_threshold_for_official", eval_cfg.get("acceptance_target_winrate", 0.90)))

    if mode == "quick":
        settings = EvalModeSettings(
            mode=mode,
            games=quick_games,
            num_workers=quick_workers,
            agent_simulations=quick_agent_simulations,
            baseline_simulations=quick_baseline_simulations,
            baseline_rollouts=quick_baseline_rollouts,
            quick_threshold_for_official=threshold,
        )
    elif mode == "official":
        settings = EvalModeSettings(
            mode=mode,
            games=official_games,
            num_workers=official_workers,
            agent_simulations=official_agent_simulations,
            baseline_simulations=official_baseline_simulations,
            baseline_rollouts=official_baseline_rollouts,
            quick_threshold_for_official=threshold,
        )
    else:
        raise KeyError(f"Unsupported eval mode: {mode}")
    resolved_override_workers = None
    if num_workers_override is not None:
        resolved_override_workers = int(num_workers_override)
        if resolved_override_workers <= 0:
            resolved_override_workers = cpu_default
    if games_override is not None:
        settings = EvalModeSettings(
            mode=settings.mode,
            games=int(games_override),
            num_workers=settings.num_workers if resolved_override_workers is None else resolved_override_workers,
            agent_simulations=settings.agent_simulations,
            baseline_simulations=settings.baseline_simulations,
            baseline_rollouts=settings.baseline_rollouts,
            quick_threshold_for_official=settings.quick_threshold_for_official,
        )
    elif resolved_override_workers is not None:
        settings = EvalModeSettings(
            mode=settings.mode,
            games=settings.games,
            num_workers=resolved_override_workers,
            agent_simulations=settings.agent_simulations,
            baseline_simulations=settings.baseline_simulations,
            baseline_rollouts=settings.baseline_rollouts,
            quick_threshold_for_official=settings.quick_threshold_for_official,
        )
    return settings


def _prepare_output_paths(output_path: str | None) -> tuple[Path | None, Path | None, Path | None]:
    if not output_path:
        return None, None, None
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    progress = target.with_name(target.stem + ".progress.json")
    games_jsonl = target.with_name(target.stem + ".games.jsonl")
    return target, progress, games_jsonl


def _baseline_step(context: EvalGameContext, adapter: AffineOpenSpielAdapter) -> tuple[int, int]:
    action = int(context.baseline.step(context.state.clone()))
    return context.game_index, adapter.codec.encode_dense(action, adapter.spec)


def _initial_progress(*, settings: EvalModeSettings, checkpoint_path: str) -> dict[str, object]:
    return {
        "ts": utc_now(),
        "status": "running",
        "mode": settings.mode,
        "checkpoint_path": checkpoint_path,
        "games_total": settings.games,
        "games_completed": 0,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "current_win_rate": 0.0,
        "first_player_wins": 0,
        "second_player_wins": 0,
        "avg_game_seconds": 0.0,
        "estimated_remaining_seconds": None,
        "agent_simulations": settings.agent_simulations,
        "baseline_simulations": settings.baseline_simulations,
        "baseline_rollouts": settings.baseline_rollouts,
        "num_workers": settings.num_workers,
    }


def _finalize_report(progress: dict[str, object]) -> dict[str, object]:
    total = int(progress["games_completed"])
    wins = int(progress["wins"])
    losses = int(progress["losses"])
    draws = int(progress["draws"])
    progress.update(
        {
            "ts": utc_now(),
            "status": "completed",
            "games": total,
            "win_rate": wins / float(max(total, 1)),
            "wins": wins,
            "losses": losses,
            "draws": draws,
        }
    )
    return progress


def os_cpu_count() -> int:
    import os

    return int(os.cpu_count() or 1)


def evaluate_checkpoint(
    *,
    config_path: str,
    checkpoint_path: str,
    games: int | None = None,
    device: str | None = None,
    seed: int = 0,
    mode: str = "quick",
    num_workers: int | None = None,
    output_path: str | None = None,
) -> dict[str, float | int | str | None]:
    config = load_yaml_config(config_path)
    spec = resolve_spec_from_config(config)
    settings = _resolve_eval_mode_settings(config, spec=spec, mode=mode, games_override=games, num_workers_override=num_workers)
    model, adapter = build_model_from_config(config)
    device_obj = default_device(device)
    model.to(device_obj)
    load_checkpoint(checkpoint_path, model=model)
    model.eval()
    search_config = clone_config(config)
    search_config.setdefault("search", {})
    search_config["search"] = dict(search_config.get("search", {}))
    search_config["search"]["eval_num_simulations"] = settings.agent_simulations
    search = build_search_engine(
        model=model,
        adapter=adapter,
        config=search_config,
        device=device_obj,
        seed=seed,
        search_overrides={"eval_num_simulations": settings.agent_simulations},
    )

    target_path, progress_path, games_path = _prepare_output_paths(output_path)
    progress_writer = JsonProgressWriter(progress_path) if progress_path is not None else None
    games_writer = JsonlEventWriter(games_path) if games_path is not None else None
    started_at = time.time()
    progress = _initial_progress(settings=settings, checkpoint_path=checkpoint_path)
    if progress_writer is not None:
        progress_writer.write(progress)

    random.seed(seed)
    pending_game_index = 0
    active: list[EvalGameContext] = []
    finished_durations: list[float] = []

    def _spawn_one(game_index: int) -> EvalGameContext:
        state = adapter.new_initial_state()
        return EvalGameContext(
            game_index=game_index,
            agent_player=game_index % 2,
            state=state,
            baseline=adapter.create_affine_mcts_bot(
                seed=seed + game_index,
                simulations=settings.baseline_simulations,
                rollouts=settings.baseline_rollouts,
            ),
        )

    while pending_game_index < settings.games and len(active) < settings.num_workers:
        active.append(_spawn_one(pending_game_index))
        pending_game_index += 1

    with ThreadPoolExecutor(max_workers=settings.num_workers) as executor:
        while active:
            agent_games = [ctx for ctx in active if not ctx.state.is_terminal() and int(ctx.state.current_player()) == ctx.agent_player]
            if agent_games:
                encoded_batch = [adapter.encode_state(ctx.state) for ctx in agent_games]
                obs_batch = torch.from_numpy(np.stack([encoded.obs for encoded in encoded_batch])).to(device_obj)
                legal_batch = torch.from_numpy(np.stack([encoded.legal_mask for encoded in encoded_batch])).to(device_obj)
                search_result = search.run(
                    obs_batch,
                    legal_batch,
                    [ctx.state for ctx in agent_games],
                    mode="eval",
                    encoded_state_batch=encoded_batch,
                )
                for index, ctx in enumerate(agent_games):
                    adapter.apply_dense_action(ctx.state, int(search_result.chosen_action[index]))
                    ctx.move_count += 1

            baseline_games = [ctx for ctx in active if not ctx.state.is_terminal() and int(ctx.state.current_player()) != ctx.agent_player]
            if baseline_games:
                futures = [executor.submit(_baseline_step, ctx, adapter) for ctx in baseline_games]
                action_by_game_index = dict(future.result() for future in futures)
                for ctx in baseline_games:
                    action = action_by_game_index[ctx.game_index]
                    adapter.apply_dense_action(ctx.state, action)
                    ctx.move_count += 1

            for ctx in list(active):
                if not ctx.state.is_terminal():
                    continue
                duration = time.time() - started_at
                finished_durations.append(duration)
                outcome = float(ctx.state.returns()[ctx.agent_player])
                if outcome > 0:
                    progress["wins"] = int(progress["wins"]) + 1
                    key = "first_player_wins" if ctx.agent_player == 0 else "second_player_wins"
                    progress[key] = int(progress[key]) + 1
                    result_label = "win"
                elif outcome < 0:
                    progress["losses"] = int(progress["losses"]) + 1
                    result_label = "loss"
                else:
                    progress["draws"] = int(progress["draws"]) + 1
                    result_label = "draw"
                progress["games_completed"] = int(progress["games_completed"]) + 1
                completed = int(progress["games_completed"])
                progress["current_win_rate"] = int(progress["wins"]) / float(max(completed, 1))
                progress["avg_game_seconds"] = float(np.mean(finished_durations))
                progress["estimated_remaining_seconds"] = eta_seconds(
                    started_at=started_at,
                    completed=completed,
                    total=settings.games,
                )
                if games_writer is not None:
                    games_writer.append(
                        {
                            "ts": utc_now(),
                            "game_index": ctx.game_index,
                            "result": result_label,
                            "outcome": outcome,
                            "agent_player": ctx.agent_player,
                            "moves": ctx.move_count,
                            "wins": progress["wins"],
                            "losses": progress["losses"],
                            "draws": progress["draws"],
                            "current_win_rate": progress["current_win_rate"],
                        }
                    )
                append_event(
                    None,
                    kind="eval_game_complete",
                    mode=settings.mode,
                    game_index=ctx.game_index,
                    result=result_label,
                    completed=completed,
                    total=settings.games,
                    current_win_rate=progress["current_win_rate"],
                    moves=ctx.move_count,
                )
                progress["ts"] = utc_now()
                if progress_writer is not None:
                    progress_writer.write(progress)
                active.remove(ctx)
                if pending_game_index < settings.games:
                    active.append(_spawn_one(pending_game_index))
                    pending_game_index += 1

    report = _finalize_report(progress)
    if target_path is not None:
        target_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if progress_writer is not None:
        progress_writer.write(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a checkpoint against the current Affine baseline MCTS")
    parser.add_argument("--config", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--games", type=int, default=0)
    parser.add_argument("--device", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--mode", choices=["quick", "official"], default="quick")
    parser.add_argument("--num-workers", type=int, default=0)
    args = parser.parse_args()

    evaluate_checkpoint(
        config_path=args.config,
        checkpoint_path=args.checkpoint,
        games=args.games or None,
        device=args.device or None,
        seed=args.seed,
        mode=args.mode,
        num_workers=args.num_workers or None,
        output_path=args.output or None,
    )


if __name__ == "__main__":
    main()
