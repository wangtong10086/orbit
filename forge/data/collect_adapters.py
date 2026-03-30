"""Framework adapters around environment-specific collection implementations."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from forge.execution.contracts import (
    GameCollectConfig,
    LivewebCollectConfig,
    MemorygymCollectConfig,
    NavworldCollectConfig,
    SweCollectConfig,
)
from forge.foundation.data_contracts import CollectResult


async def collect_navworld(config: NavworldCollectConfig, staging_path: str) -> CollectResult:
    from forge.data.navworld_gen import generate_batch

    amap_key = os.environ.get("AMAP_API_KEY") or os.environ.get("AMAP_MAPS_API_KEY", "")
    api_key = os.environ.get("QWEN_API_KEY") or os.environ.get("CHUTES_API_KEY", "")
    if not amap_key:
        raise RuntimeError("AMAP_API_KEY or AMAP_MAPS_API_KEY not set")
    if not api_key:
        raise RuntimeError("QWEN_API_KEY or CHUTES_API_KEY not set")

    await generate_batch(
        num_samples=config.num,
        output_path=staging_path,
        amap_key=amap_key,
        api_key=api_key,
        model=config.model,
        start_id=config.start_id,
        concurrency=config.concurrency,
        problem_type=config.problem_type,
    )
    records = 0
    with open(staging_path, encoding="utf-8") as handle:
        records = sum(1 for line in handle if line.strip())
    return CollectResult(
        output=staging_path,
        staging_path=staging_path,
        records=records,
        success=records,
        failed=max(config.num - records, 0),
    )


async def collect_liveweb(config: LivewebCollectConfig, staging_path: str) -> CollectResult:
    from forge.data.liveweb_gen import generate_liveweb_data
    from forge.data.liveweb_teacher_gen import (
        check_stooq_cache,
        generate_liveweb_teacher_data,
        parse_seed_range,
        teacher_pipeline_ready,
    )

    cache_dir = config.cache_dir or os.environ.get("LIVEWEB_CACHE_DIR", "")
    if cache_dir:
        teacher_ready, teacher_reason = teacher_pipeline_ready(cache_dir)
    else:
        teacher_ready, teacher_reason = False, "cache dir missing"
    seed_range = parse_seed_range(config.seeds)
    plugins = list(config.plugins)
    subtasks = list(config.subtasks)

    if teacher_ready:
        if "stooq" in plugins:
            warning = check_stooq_cache(cache_dir)
            if warning:
                print(f"[WARN] {warning}")
        result = await generate_liveweb_teacher_data(
            seeds=seed_range,
            subtasks=subtasks,
            include_plugins=plugins,
            cache_dir=cache_dir,
            output_path=staging_path,
            concurrency=config.concurrency,
        )
        return CollectResult.model_validate(
            {
                **result,
                "output": result.get("output", staging_path),
                "staging_path": staging_path,
                "success": result.get("records", 0),
                "failed": result.get("errors", 0),
                "mode": "teacher",
            }
        )

    result = await generate_liveweb_data(
        output=staging_path,
        seed_values=list(seed_range),
        subtasks=subtasks,
        include_plugins=plugins,
        min_score=config.min_score,
        timeout=config.timeout,
        use_cache=False,
        cache_dir=None,
    )
    return CollectResult.model_validate(
        {
            **result,
            "output": result.get("output", staging_path),
            "staging_path": staging_path,
            "success": result.get("records", 0),
            "mode": f"live-fallback ({teacher_reason})",
        }
    )


def collect_game(config: GameCollectConfig, staging_path: str) -> CollectResult:
    from forge.data.game_gen import generate_game_data

    result = generate_game_data(
        output_path=staging_path,
        game_name=config.game_name or None,
        all_games=config.all_games,
        sample_count=config.num,
        start_seed=config.start_seed,
        attempt_multiplier=config.attempt_multiplier,
        generator_source=config.generator_source,
    )
    return CollectResult(
        **result,
        success=result.get("records", 0),
    )


def collect_memorygym(config: MemorygymCollectConfig, raw_path: str, staging_path: str) -> CollectResult:
    from forge.data.memorygym_gen import generate_dataset
    from forge.data.memorygym_split import split_dataset

    raw_result = generate_dataset(
        output=raw_path,
        templates=list(config.templates) or None,
        seeds=config.seeds,
        tier=config.tier,
        tier_mix=config.tier_mix,
        workers=config.jobs,
    )
    split_result = split_dataset(
        input_path=raw_path,
        output_path=staging_path,
        target=config.target,
        balance=config.balance,
        shuffle_seed=config.shuffle_seed,
    )
    return CollectResult.model_validate(
        {
            **split_result,
            "raw_path": raw_path,
            "staging_path": staging_path,
            "output": split_result.get("output", staging_path),
            "trajectories": raw_result.get("trajectories", 0),
            "records": split_result.get("samples", 0),
            "success": split_result.get("samples", 0),
            "samples": split_result.get("samples", 0),
            "distribution": split_result.get("distribution", {}),
        }
    )


def collect_memorygym_split(
    *,
    input_path: str,
    output_path: str,
    target: int,
    balance: bool,
    shuffle_seed: int,
) -> CollectResult:
    from forge.data.memorygym_split import split_dataset

    result = split_dataset(
        input_path=input_path,
        output_path=output_path,
        target=target,
        balance=balance,
        shuffle_seed=shuffle_seed,
    )
    return CollectResult.model_validate(
        {
            **result,
            "output": result.get("output", output_path),
            "staging_path": output_path,
            "records": result.get("samples", 0),
            "success": result.get("samples", 0),
        }
    )


def collect_swe(config: SweCollectConfig, canonical_dir: str, raw_dir: str, staging_path: str) -> CollectResult:
    from forge.data.swe_ops import sync_new_trajectories

    result = sync_new_trajectories(
        dry_run=False,
        machine=config.machine or None,
        canonical_dir=canonical_dir,
        staging_path=staging_path,
        raw_output_dir=raw_dir,
    )
    return CollectResult.model_validate(
        {
            **result,
            "output": staging_path,
            "staging_path": staging_path,
            "records": result.get("new_count", 0),
            "success": result.get("new_count", 0),
        }
    )


async def collect_from_config(config, *, staging_path: str, raw_dir: str = "", canonical_dir: str = "") -> CollectResult:
    if isinstance(config, NavworldCollectConfig):
        return await collect_navworld(config, staging_path)
    if isinstance(config, LivewebCollectConfig):
        return await collect_liveweb(config, staging_path)
    if isinstance(config, GameCollectConfig):
        return collect_game(config, staging_path)
    if isinstance(config, MemorygymCollectConfig):
        raw_path = str(Path(raw_dir) / f"{Path(staging_path).stem}_raw.jsonl")
        return collect_memorygym(config, raw_path, staging_path)
    if isinstance(config, SweCollectConfig):
        return collect_swe(config, canonical_dir, raw_dir, staging_path)
    raise RuntimeError(f"Unsupported collect config: {type(config).__name__}")


def run_collect_from_config(config, *, staging_path: str, raw_dir: str = "", canonical_dir: str = "") -> CollectResult:
    return asyncio.run(
        collect_from_config(
            config,
            staging_path=staging_path,
            raw_dir=raw_dir,
            canonical_dir=canonical_dir,
        )
    )
