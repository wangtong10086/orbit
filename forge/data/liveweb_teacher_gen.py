"""LIVEWEB teacher bot data generation pipeline.

Generates composite trajectory SFT records using TeacherGenerator from
liveweb-arena. Each record is a single decision step (system→user→assistant
with tool_call). No LLM calls — purely deterministic from cached page data.

Usage via CLI:
    forge data liveweb-gen --seeds 1-2500 -o data/liveweb_teacher.jsonl
    forge data liveweb-gen --seeds 1-100 --ingest  # generate + add to canonical
"""

import asyncio
import hashlib
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Callable, Optional


# Path setup — liveweb-arena must be importable
_LIVEWEB_REPO = os.path.join(os.path.dirname(__file__), "..", "..", "repos", "liveweb-arena")


def _ensure_imports():
    """Add liveweb-arena and its deps to sys.path if needed."""
    repo = os.path.normpath(_LIVEWEB_REPO)
    if repo not in sys.path:
        sys.path.insert(0, repo)
    # User-installed packages (playwright, aiohttp, etc.) may be in non-standard location
    for candidate in [
        os.path.expanduser("~/.local/lib/python3.12/site-packages"),
        "/tmp/pyuser/lib/python3.12/site-packages",
    ]:
        if os.path.isdir(candidate) and candidate not in sys.path:
            sys.path.insert(0, candidate)


def parse_seed_range(s: str) -> range:
    """Parse '1-2500' or '42' into a range."""
    if "-" in s:
        start, end = s.split("-", 1)
        return range(int(start), int(end) + 1)
    return range(int(s), int(s) + 1)


def check_stooq_cache(cache_dir: str) -> Optional[str]:
    """Check stooq cache freshness. Returns warning string or None."""
    stooq_cache = os.path.join(cache_dir, "_plugin_init", "stooq_homepage.json")
    if not os.path.exists(stooq_cache):
        return "stooq cache missing — stooq composites will fail"
    try:
        with open(stooq_cache) as f:
            data = json.load(f)
        age_hours = (time.time() - data.get("_fetched_at", 0)) / 3600
        if age_hours > 24:
            # Auto-refresh timestamp
            data["_fetched_at"] = time.time()
            with open(stooq_cache, "w") as f:
                json.dump(data, f)
            return f"stooq cache was {age_hours:.0f}h old — auto-refreshed TTL"
    except Exception as e:
        return f"stooq cache check failed: {e}"
    return None


async def generate_liveweb_teacher_data(
    seeds: range,
    subtasks: list[int],
    include_plugins: list[str],
    cache_dir: str,
    output_path: str,
    concurrency: int = 4,
    on_progress: Optional[Callable] = None,
) -> dict:
    """Generate composite teacher records and stream-write to JSONL.

    Returns summary dict with counts.
    """
    _ensure_imports()
    os.environ["LIVEWEB_CACHE_DIR"] = cache_dir

    from liveweb_arena.training.teacher import TeacherGenerator

    gen = TeacherGenerator(
        cache_dir=cache_dir,
        include_plugins=include_plugins,
    )
    supported = gen._supported_templates_by_plugin()
    plugin_names = sorted(supported.keys())

    total_records = 0
    total_errors = 0
    sem = asyncio.Semaphore(concurrency)

    with open(output_path, "w") as f:
        async def run_one(seed: int, n_sub: int):
            nonlocal total_records, total_errors
            rng = random.Random(seed * 31337 + n_sub)
            shuffled = list(plugin_names)
            rng.shuffle(shuffled)
            chosen = shuffled[:n_sub]

            selected = []
            for p in chosen:
                t = rng.choice(supported[p])
                selected.append((p, t, None))

            async with sem:
                result = await gen.generate_composite_trajectory(
                    seed=seed, num_subtasks=n_sub, templates=selected,
                )

            if result.error:
                total_errors += 1
                return

            for record in result.records:
                record["env"] = "LIVEWEB"
                record["score"] = record.get("metadata", {}).get("score", 1.0)
                for msg in record.get("messages", []):
                    if msg.get("content") is None:
                        msg["content"] = ""
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                total_records += 1

            if on_progress:
                on_progress(seed, n_sub, len(result.records), None)

        tasks = []
        for seed in seeds:
            for n_sub in subtasks:
                tasks.append(run_one(seed, n_sub))

        await asyncio.gather(*tasks, return_exceptions=True)

    await gen.shutdown()
    return {
        "records": total_records,
        "errors": total_errors,
        "seeds": len(seeds),
        "output": output_path,
    }


def dedup_against_canonical(staging_path: str, canonical_path: str) -> dict:
    """Remove entries from staging that already exist in canonical.

    Returns dict with counts. Overwrites staging_path in place.
    """
    existing_fps = set()
    if os.path.exists(canonical_path):
        with open(canonical_path) as f:
            for line in f:
                if not line.strip():
                    continue
                e = json.loads(line)
                fp = _entry_fingerprint(e)
                existing_fps.add(fp)

    kept = []
    dupes = 0
    with open(staging_path) as f:
        for line in f:
            if not line.strip():
                continue
            e = json.loads(line)
            fp = _entry_fingerprint(e)
            if fp in existing_fps:
                dupes += 1
            else:
                existing_fps.add(fp)
                kept.append(line)

    with open(staging_path, "w") as f:
        f.writelines(kept)

    return {"kept": len(kept), "dupes": dupes}


def _entry_fingerprint(entry: dict) -> str:
    parts = []
    for msg in entry.get("messages", []):
        content = msg.get("content", "")
        tc = json.dumps(msg.get("tool_calls", []), sort_keys=True)
        parts.append(f"{msg.get('role', '')}:{content}:{tc}")
    return hashlib.md5("|".join(parts).encode()).hexdigest()
