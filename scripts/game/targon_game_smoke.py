"""Remote GAME smoke entrypoint for Targon serverless validation."""

from __future__ import annotations

import json
import os
from pathlib import Path

from forge.data.game_gen import generate_game_data
from forge.data.game_generators.policy_generators import build_policy_snapshot
from forge.data.game_policy_models import (
    build_expert_dataset,
    default_policy_model_dir,
    evaluate_selfplay_policy_model,
    resume_selfplay_policy_model,
    train_policy_model,
    train_selfplay_policy_model,
)
from forge.data.game_trajectory_generators import resolve_game_trajectory_generator


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "")
    return int(raw) if raw else default


def _env_positive_int(name: str, default: int) -> int:
    value = _env_int(name, default)
    return value if value > 0 else default


def main() -> None:
    game = os.environ["AFFINE_GAME_NAME"]
    sample_count = _env_int("AFFINE_GAME_SAMPLE_COUNT", 2)
    start_seed = _env_int("AFFINE_GAME_START_SEED", 100000)
    attempt_multiplier = _env_int("AFFINE_GAME_ATTEMPT_MULTIPLIER", 4)
    generator_source = os.environ.get("AFFINE_GAME_GENERATOR_SOURCE", "default")
    build_policy = os.environ.get("AFFINE_GAME_BUILD_POLICY", "0") == "1"
    build_expert = os.environ.get("AFFINE_GAME_BUILD_EXPERT_DATASET", "0") == "1"
    train_policy_model_flag = os.environ.get("AFFINE_GAME_TRAIN_POLICY_MODEL", "0") == "1"
    selfplay_train_flag = os.environ.get("AFFINE_GAME_SELFPLAY_TRAIN", "0") == "1"
    selfplay_resume_flag = os.environ.get("AFFINE_GAME_SELFPLAY_RESUME", "0") == "1"
    selfplay_eval_opponent = os.environ.get("AFFINE_GAME_SELFPLAY_EVAL_OPPONENT", "")
    policy_iterations = _env_int("AFFINE_GAME_POLICY_ITERATIONS", 0)
    expert_samples = _env_positive_int("AFFINE_GAME_EXPERT_SAMPLES", max(sample_count * 4, 8))
    policy_epochs = _env_positive_int("AFFINE_GAME_POLICY_EPOCHS", 10)
    policy_batch_size = _env_positive_int("AFFINE_GAME_POLICY_BATCH_SIZE", 512)
    policy_hidden_dim = _env_positive_int("AFFINE_GAME_POLICY_HIDDEN_DIM", 256)
    policy_device = os.environ.get("AFFINE_GAME_POLICY_DEVICE", "")
    selfplay_episodes = _env_positive_int("AFFINE_GAME_SELFPLAY_EPISODES", max(sample_count * 8, 32))
    selfplay_simulations = _env_positive_int("AFFINE_GAME_SELFPLAY_SIMULATIONS", 64)
    selfplay_quick_games = _env_positive_int("AFFINE_GAME_SELFPLAY_QUICK_GAMES", 50)
    selfplay_teacher_games = _env_positive_int("AFFINE_GAME_SELFPLAY_TEACHER_GAMES", 200)
    selfplay_repo = os.environ.get("AFFINE_GAME_POLICY_REPO", "")

    spec = resolve_game_trajectory_generator(game)
    print(
        "BUILD::"
        + json.dumps(
            {
                "game": game,
                "generator_name": spec.name,
                "generator_family": spec.family,
                "game_params": spec.game_params,
                "policy_path": spec.policy_path,
            },
            ensure_ascii=False,
        )
    )

    if build_policy and spec.family in {"cfr", "mccfr", "deep_cfr"}:
        report = build_policy_snapshot(
            game_name=game,
            generator_name=spec.name,
            family=spec.family,
            params=spec.game_params,
            output_path=spec.policy_path,
            iterations=policy_iterations or spec.default_iterations,
        )
        print("POLICY::" + json.dumps(report.model_dump(mode="json"), ensure_ascii=False))

    expert_dataset_path = f"/tmp/affine-swarm/artifacts/game_expert_datasets/{game}/expert_dataset.npz"
    if build_expert:
        report = build_expert_dataset(
            game_name=game,
            output_path=expert_dataset_path,
            trajectory_target=expert_samples,
            start_seed=start_seed,
            attempt_multiplier=attempt_multiplier,
            build_policy_if_missing=build_policy,
            policy_iterations=policy_iterations,
        )
        print("EXPERT::" + json.dumps(report.model_dump(mode="json"), ensure_ascii=False))

    if train_policy_model_flag:
        report = train_policy_model(
            game_name=game,
            dataset_path=expert_dataset_path,
            output_dir=default_policy_model_dir(game),
            hidden_dim=policy_hidden_dim,
            batch_size=policy_batch_size,
            epochs=policy_epochs,
            device=policy_device,
        )
        print("MODEL::" + json.dumps(report.model_dump(mode="json"), ensure_ascii=False))

    if selfplay_train_flag:
        report = train_selfplay_policy_model(
            game_name=game,
            output_dir=default_policy_model_dir(game),
            selfplay_episodes=selfplay_episodes,
            start_seed=start_seed,
            simulations=selfplay_simulations,
            epochs=policy_epochs,
            batch_size=policy_batch_size,
            learning_rate=3e-4,
            weight_decay=1e-4,
            device=policy_device,
            quick_gate_games=selfplay_quick_games,
            teacher_gate_games=selfplay_teacher_games,
            resume=True,
            repo_id=selfplay_repo,
        )
        print("SELFPLAY::" + json.dumps(report.model_dump(mode="json"), ensure_ascii=False))

    if selfplay_resume_flag:
        report = resume_selfplay_policy_model(
            game_name=game,
            output_dir=default_policy_model_dir(game),
            selfplay_episodes=selfplay_episodes,
            start_seed=start_seed,
            simulations=selfplay_simulations,
            epochs=policy_epochs,
            batch_size=policy_batch_size,
            learning_rate=3e-4,
            weight_decay=1e-4,
            device=policy_device,
            quick_gate_games=selfplay_quick_games,
            teacher_gate_games=selfplay_teacher_games,
            repo_id=selfplay_repo,
        )
        print("SELFPLAY::" + json.dumps(report.model_dump(mode="json"), ensure_ascii=False))

    if selfplay_eval_opponent:
        report = evaluate_selfplay_policy_model(
            game_name=game,
            output_dir=default_policy_model_dir(game),
            opponent=selfplay_eval_opponent,
            games=selfplay_teacher_games if selfplay_eval_opponent == "teacher" else selfplay_quick_games,
        )
        print("ARENA::" + json.dumps(report.model_dump(mode="json"), ensure_ascii=False))

    output = f"/tmp/affine-swarm/tmp/targon_{game}.jsonl"
    result = generate_game_data(
        output_path=output,
        game_name=game,
        sample_count=sample_count,
        start_seed=start_seed,
        attempt_multiplier=attempt_multiplier,
        generator_source=generator_source,
    )
    print("GENERATE::" + json.dumps(result, ensure_ascii=False))

    output_path = Path(output)
    if output_path.exists():
        with output_path.open(encoding="utf-8") as handle:
            for idx, line in enumerate(handle):
                if idx >= 2:
                    break
                if line.strip():
                    print("PREVIEW::" + line.rstrip())


if __name__ == "__main__":
    main()
