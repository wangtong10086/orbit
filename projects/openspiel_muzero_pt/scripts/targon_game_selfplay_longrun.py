"""Long-running remote self-play entrypoint for GAME policy training."""

from __future__ import annotations

import json
import os

from orbit.data.game_policy_models import default_policy_model_dir, train_selfplay_until_gate


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "")
    return int(raw) if raw else default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "")
    return float(raw) if raw else default


def main() -> None:
    game = os.environ["AFFINE_GAME_NAME"]
    output_dir = os.environ.get("AFFINE_GAME_POLICY_MODEL_DIR", default_policy_model_dir(game))
    start_seed = _env_int("AFFINE_GAME_START_SEED", 100000)
    episodes = _env_int("AFFINE_GAME_SELFPLAY_EPISODES", 64)
    simulations = _env_int("AFFINE_GAME_SELFPLAY_SIMULATIONS", 128)
    epochs = _env_int("AFFINE_GAME_POLICY_EPOCHS", 2)
    batch_size = _env_int("AFFINE_GAME_POLICY_BATCH_SIZE", 4096)
    learning_rate = _env_float("AFFINE_GAME_POLICY_LR", 3e-4)
    weight_decay = _env_float("AFFINE_GAME_POLICY_WEIGHT_DECAY", 1e-4)
    quick_gate_games = _env_int("AFFINE_GAME_SELFPLAY_QUICK_GAMES", 50)
    quick_gate_min_win_rate = _env_float("AFFINE_GAME_SELFPLAY_QUICK_MIN_WIN_RATE", 0.55)
    teacher_gate_games = _env_int("AFFINE_GAME_SELFPLAY_TEACHER_GAMES", 200)
    teacher_gate_min_win_rate = _env_float("AFFINE_GAME_SELFPLAY_TEACHER_MIN_WIN_RATE", 0.90)
    teacher_gate_required_streak = _env_int("AFFINE_GAME_SELFPLAY_REQUIRED_STREAK", 2)
    quick_gate_interval = _env_int("AFFINE_GAME_SELFPLAY_QUICK_INTERVAL", 1)
    teacher_gate_interval = _env_int("AFFINE_GAME_SELFPLAY_TEACHER_INTERVAL", 1)
    sync_interval = _env_int("AFFINE_GAME_SELFPLAY_SYNC_INTERVAL", 10)
    autotune_batch = os.environ.get("AFFINE_GAME_SELFPLAY_AUTOTUNE_BATCH", "0") == "1"
    device = os.environ.get("AFFINE_GAME_POLICY_DEVICE", "")
    repo_id = os.environ.get("AFFINE_GAME_POLICY_REPO", "")
    max_rounds = _env_int("AFFINE_GAME_SELFPLAY_MAX_ROUNDS", 200)
    resume = os.environ.get("AFFINE_GAME_SELFPLAY_RESUME", "1") == "1"

    print(
        "LONGRUN_CONFIG::"
        + json.dumps(
            {
                "game": game,
                "output_dir": output_dir,
                "episodes": episodes,
                "simulations": simulations,
                "epochs": epochs,
                "batch_size": batch_size,
                "learning_rate": learning_rate,
                "weight_decay": weight_decay,
                "quick_gate_games": quick_gate_games,
                "quick_gate_min_win_rate": quick_gate_min_win_rate,
                "teacher_gate_games": teacher_gate_games,
                "teacher_gate_min_win_rate": teacher_gate_min_win_rate,
                "teacher_gate_required_streak": teacher_gate_required_streak,
                "quick_gate_interval": quick_gate_interval,
                "teacher_gate_interval": teacher_gate_interval,
                "sync_interval": sync_interval,
                "autotune_batch": autotune_batch,
                "device": device,
                "repo_id": repo_id,
                "max_rounds": max_rounds,
                "resume": resume,
            },
            ensure_ascii=False,
        )
    )

    report = train_selfplay_until_gate(
        game_name=game,
        output_dir=output_dir,
        selfplay_episodes=episodes,
        start_seed=start_seed,
        simulations=simulations,
        epochs=epochs,
        batch_size=batch_size,
        learning_rate=learning_rate,
        weight_decay=weight_decay,
        device=device,
        quick_gate_games=quick_gate_games,
        quick_gate_min_win_rate=quick_gate_min_win_rate,
        teacher_gate_games=teacher_gate_games,
        teacher_gate_min_win_rate=teacher_gate_min_win_rate,
        teacher_gate_required_streak=teacher_gate_required_streak,
        quick_gate_interval_updates=quick_gate_interval,
        teacher_gate_interval_updates=teacher_gate_interval,
        sync_interval_updates=sync_interval,
        autotune_batch_size=autotune_batch,
        resume=resume,
        repo_id=repo_id,
        max_rounds=max_rounds,
    )
    print("LONGRUN_RESULT::" + json.dumps(report.model_dump(mode="json"), ensure_ascii=False))


if __name__ == "__main__":
    main()
