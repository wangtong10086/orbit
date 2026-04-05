"""SFT data extraction, quality filtering, and analysis."""

import json
import os
import re
import time
from typing import Optional

from orbit.foundation.environment_catalog import default_environment_catalog


# ===== Environment-specific cleaners =====
# COMPATIBILITY LAYER: delegates to orbit.env.* implementations.
# Old code can still call these directly; new code should use EnvironmentCatalog.

CATALOG = default_environment_catalog()

def _clean_game(record: dict) -> Optional[dict]:
    return CATALOG.make_data("GAME").clean_entry(record)

def _clean_lgc(record: dict) -> Optional[dict]:
    return CATALOG.make_data("LGC-v2").clean_entry(record)

def _clean_print(record: dict) -> Optional[dict]:
    return CATALOG.make_data("PRINT").clean_entry(record)

def _clean_swe_synth(record: dict) -> Optional[dict]:
    return CATALOG.make_data("SWE-INFINITE").clean_entry(record)

def _clean_navworld(record: dict) -> Optional[dict]:
    return CATALOG.make_data("NAVWORLD").clean_entry(record)

def _clean_liveweb(record: dict) -> Optional[dict]:
    return CATALOG.make_data("LIVEWEB").clean_entry(record)


# Keep NAVWORLD constants available for backward compat
NAVWORLD_REASONING_WORDS = re.compile(
    r"因为|由于|所以|因此|建议|推荐|考虑到|综合|权衡|对比|相比|优先|适合"
)
NAVWORLD_TOOLS = {"poi_search", "around_search", "weather", "direction", "search_flights", "search_train_tickets"}


# Registry: env name -> cleaner function
ENV_CLEANERS: dict[str, callable] = {
    "GAME": _clean_game,
    "LGC-v2": _clean_lgc,
    "PRINT": _clean_print,
    "SWE-INFINITE": _clean_swe_synth,
    "NAVWORLD": _clean_navworld,
    "LIVEWEB": _clean_liveweb,
}


def extract_sft_record(record: dict, env: str) -> Optional[dict]:
    """Extract SFT-ready conversation from a sample record.

    Extracts messages, then applies env-specific cleaning.
    Returns dict with 'messages' in chat format, or None if unusable.
    """
    extra = record.get("extra", {})
    if not extra:
        return None

    sft = None

    # Try conversation format (most common)
    conversation = extra.get("conversation", [])
    if conversation and isinstance(conversation, list):
        messages = []
        for msg in conversation:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if content:
                messages.append({"role": role, "content": content})

        if messages:
            sft = {
                "messages": messages,
                "score": record.get("score", 0.0),
                "env": env,
                "task_id": record.get("task_id"),
            }

    # Try request/response format
    if not sft:
        request = extra.get("request", {})
        response = extra.get("response", "")
        if request and response:
            messages = []
            if isinstance(request, dict):
                msgs = request.get("messages", [])
                if msgs:
                    messages = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in msgs]
            if isinstance(response, str):
                messages.append({"role": "assistant", "content": response})

            if messages:
                sft = {
                    "messages": messages,
                    "score": record.get("score", 0.0),
                    "env": env,
                    "task_id": record.get("task_id"),
                }

    if not sft:
        return None

    # Apply env-specific cleaning
    cleaner = ENV_CLEANERS.get(env)
    if cleaner:
        sft = cleaner(sft)

    return sft


def validate_navworld(records: list[dict]) -> dict:
    """Deep quality audit of NAVWORLD data. Delegates to NavworldEnv.deep_validate()."""
    return CATALOG.make_data("NAVWORLD").deep_validate(records)


def char_length(record: dict) -> int:
    """Total character length of all messages in a record."""
    return sum(len(m.get("content", "")) for m in record.get("messages", []))


def filter_quality(
    records: list[dict],
    min_score: float = 0.5,
    max_chars: int = 0,
    dedup: bool = True,
) -> list[dict]:
    """Filter records by quality score, length, and optionally deduplicate.

    Args:
        records: Raw SFT records
        min_score: Minimum score threshold
        max_chars: Max total character length (0=unlimited). Recommended ~16000 for 4K token context.
        dedup: Deduplicate by (env, task_id), keeping highest score
    """
    filtered = [r for r in records if r.get("score", 0.0) >= min_score]

    if max_chars > 0:
        filtered = [r for r in filtered if char_length(r) <= max_chars]

    if dedup:
        # Keep highest score per (env, task_id)
        best = {}
        for r in filtered:
            key = (r.get("env"), r.get("task_id"))
            if key not in best or r.get("score", 0) > best[key].get("score", 0):
                best[key] = r
        filtered = list(best.values())

    # Sort by score descending (best first)
    filtered.sort(key=lambda r: r.get("score", 0), reverse=True)
    return filtered


def analyze_dataset(path: str) -> dict:
    """Analyze a JSONL dataset file and return quality metrics."""
    with open(path) as f:
        records = [json.loads(line) for line in f]

    if not records:
        return {"count": 0}

    scores = [r.get("score", 0) for r in records]
    lengths = [char_length(r) for r in records]
    turns = [len(r.get("messages", [])) for r in records]

    scores.sort()
    lengths.sort()

    score_buckets = {}
    for threshold in [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
        score_buckets[f">={threshold}"] = sum(1 for s in scores if s >= threshold)

    return {
        "count": len(records),
        "score": {
            "min": scores[0],
            "max": scores[-1],
            "mean": sum(scores) / len(scores),
            "median": scores[len(scores) // 2],
            "buckets": score_buckets,
        },
        "char_length": {
            "min": lengths[0],
            "max": lengths[-1],
            "mean": sum(lengths) / len(lengths),
            "median": lengths[len(lengths) // 2],
            "over_16k": sum(1 for l in lengths if l > 16000),
        },
        "turns": {
            "min": min(turns),
            "max": max(turns),
            "mean": sum(turns) / len(turns),
        },
        "envs": dict(sorted(
            {env: count for env, count in
             ((e, sum(1 for r in records if r.get("env") == e))
              for e in set(r.get("env") for r in records))}.items(),
            key=lambda x: -x[1],
        )),
    }


def merge_datasets(
    input_paths: list[str],
    output_path: str,
    env_weights: Optional[dict[str, float]] = None,
    max_per_env: int = 0,
    min_score: float = 0.0,
) -> dict:
    """Merge multiple JSONL datasets with optional per-env weighting.

    Args:
        input_paths: List of JSONL file paths
        output_path: Output JSONL path
        env_weights: Optional {env_name: weight} for sampling. Higher weight = more samples.
                     Default: proportional to scheduling weight (GAME=3x).
        max_per_env: Max records per environment (0=unlimited)
        min_score: Additional score filter
    """
    import random

    all_records = []
    for path in input_paths:
        with open(path) as f:
            for line in f:
                r = json.loads(line)
                if r.get("score", 0) >= min_score:
                    all_records.append(r)

    # Group by env
    by_env: dict[str, list[dict]] = {}
    for r in all_records:
        env = r.get("env", "unknown")
        by_env.setdefault(env, []).append(r)

    # Sort each env by score descending
    for env in by_env:
        by_env[env].sort(key=lambda r: r.get("score", 0), reverse=True)

    # Apply max_per_env
    if max_per_env > 0:
        for env in by_env:
            by_env[env] = by_env[env][:max_per_env]

    # Merge and shuffle
    merged = []
    for records in by_env.values():
        merged.extend(records)
    random.shuffle(merged)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        for r in merged:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    env_counts = {env: len(recs) for env, recs in sorted(by_env.items(), key=lambda x: -len(x[1]))}
    return {"total": len(merged), "by_env": env_counts, "output": output_path}

