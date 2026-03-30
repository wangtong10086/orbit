"""Long-running GAME training and collection job entrypoint."""

from __future__ import annotations

import json
import os

from forge.data.game_longrun import GameLongRunConfig, default_longrun_root, run_game_longrun_job


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "")
    return int(raw) if raw else default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "")
    return float(raw) if raw else default


def main() -> None:
    job_name = os.environ.get("AFFINE_GAME_LONGRUN_JOB_NAME", "game-longrun")
    config = GameLongRunConfig(
        job_name=job_name,
        root_dir=os.environ.get("AFFINE_GAME_LONGRUN_ROOT", default_longrun_root(job_name)),
        perfect_target=_env_int("AFFINE_GAME_LONGRUN_PERFECT_TARGET", 100_000),
        imperfect_target=_env_int("AFFINE_GAME_LONGRUN_IMPERFECT_TARGET", 100_000),
        perfect_chunk=_env_int("AFFINE_GAME_LONGRUN_PERFECT_CHUNK", 5_000),
        imperfect_chunk=_env_int("AFFINE_GAME_LONGRUN_IMPERFECT_CHUNK", 5_000),
        selfplay_episodes=_env_int("AFFINE_GAME_LONGRUN_SELFPLAY_EPISODES", 256),
        selfplay_simulations=_env_int("AFFINE_GAME_LONGRUN_SELFPLAY_SIMULATIONS", 128),
        selfplay_epochs=_env_int("AFFINE_GAME_LONGRUN_SELFPLAY_EPOCHS", 2),
        batch_size=_env_int("AFFINE_GAME_LONGRUN_BATCH_SIZE", 2048),
        learning_rate=_env_float("AFFINE_GAME_LONGRUN_LR", 5e-4),
        weight_decay=_env_float("AFFINE_GAME_LONGRUN_WEIGHT_DECAY", 1e-4),
        device=os.environ.get("AFFINE_GAME_LONGRUN_DEVICE", ""),
        quick_gate_games=_env_int("AFFINE_GAME_LONGRUN_QUICK_GAMES", 50),
        quick_gate_min_win_rate=_env_float("AFFINE_GAME_LONGRUN_QUICK_MIN_WIN_RATE", 0.52),
        teacher_gate_games=_env_int("AFFINE_GAME_LONGRUN_TEACHER_GAMES", 200),
        teacher_gate_min_win_rate=_env_float("AFFINE_GAME_LONGRUN_TEACHER_MIN_WIN_RATE", 0.90),
        teacher_gate_required_streak=_env_int("AFFINE_GAME_LONGRUN_REQUIRED_STREAK", 1),
        max_rounds_per_game=_env_int("AFFINE_GAME_LONGRUN_MAX_ROUNDS", 200),
        perfect_attempt_multiplier=_env_int("AFFINE_GAME_LONGRUN_PERFECT_ATTEMPTS", 4),
        imperfect_attempt_multiplier=_env_int("AFFINE_GAME_LONGRUN_IMPERFECT_ATTEMPTS", 8),
        seed_stride=_env_int("AFFINE_GAME_LONGRUN_SEED_STRIDE", 1_000_000),
        policy_repo_id=os.environ.get("AFFINE_GAME_POLICY_REPO", ""),
    )
    print("JOB_CONFIG::" + json.dumps(config.model_dump(mode="json"), ensure_ascii=False))
    result = run_game_longrun_job(config)
    print("JOB_RESULT::" + json.dumps(result.model_dump(mode="json"), ensure_ascii=False))


if __name__ == "__main__":
    main()
