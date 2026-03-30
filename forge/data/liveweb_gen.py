"""LIVEWEB training data generator using the installed liveweb-arena repo.

This module is the local fallback when the teacher-bot pipeline is unavailable
or no prepared cache is present. It drives liveweb-arena directly against a
real browser/LLM backend and writes canonical-ready JSONL records.
"""

import asyncio
import json
import os
import random
import sys
from pathlib import Path
from typing import Callable, Optional

LIVEWEB_ARENA_PATH = Path(__file__).parent.parent.parent / "repos" / "liveweb-arena"


def _ensure_playwright():
    """Ensure Playwright browsers are available."""
    browsers_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/tmp/pw-browsers")
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browsers_path
    if not Path(browsers_path).exists() or not list(Path(browsers_path).glob("chromium*")):
        print("Installing Playwright Chromium...")
        import subprocess
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"],
                       env={**os.environ, "PLAYWRIGHT_BROWSERS_PATH": browsers_path},
                       check=True)


def _setup_path():
    """Add liveweb-arena to Python path."""
    arena_str = str(LIVEWEB_ARENA_PATH)
    if arena_str not in sys.path:
        sys.path.insert(0, arena_str)


def _normalize_base_url(base_url: str) -> str:
    if base_url.endswith("/v1"):
        return base_url
    return base_url.rstrip("/") + "/v1"


def _resolve_liveweb_llm() -> tuple[str, str, str]:
    """Resolve an OpenAI-compatible model/base_url/api_key triple."""
    chutes_key = os.getenv("CHUTES_API_KEY", "")
    if chutes_key:
        return (
            os.getenv("LIVEWEB_MODEL", "zai-org/GLM-4.7-TEE"),
            os.getenv("LIVEWEB_BASE_URL", "https://llm.chutes.ai"),
            chutes_key,
        )

    api_key = os.getenv("API_KEY", "")
    if api_key:
        return (
            os.getenv("LIVEWEB_MODEL", "zai-org/GLM-4.7-TEE"),
            os.getenv("API_BASE_URL", "https://llm.chutes.ai"),
            api_key,
        )

    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_base = os.getenv("ANTHROPIC_BASE_URL", "")
    if anthropic_key and anthropic_base:
        return (
            os.getenv("LIVEWEB_MODEL", "claude-sonnet-4-20250514"),
            anthropic_base,
            anthropic_key,
        )

    raise RuntimeError(
        "LIVEWEB generation requires one of CHUTES_API_KEY, API_KEY, or "
        "ANTHROPIC_API_KEY+ANTHROPIC_BASE_URL in .env/environment"
    )


def _template_pool(include_plugins: list[str] | None) -> list[tuple[str, str, None]]:
    _setup_path()
    from liveweb_arena.core.task_registry import TaskRegistry

    plugins = set(include_plugins or [])
    templates: list[tuple[str, str, None]] = []
    for plugin_name, template_name in TaskRegistry.TEMPLATES.values():
        if plugins and plugin_name not in plugins:
            continue
        templates.append((plugin_name, template_name, None))
    if not templates:
        raise RuntimeError(f"No LIVEWEB templates available for plugins: {sorted(plugins)}")
    return templates


async def generate_liveweb_data(
    output: str = "data/liveweb_claude.jsonl",
    seed_values: list[int] | None = None,
    subtasks: list[int] | None = None,
    include_plugins: list[str] | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    min_score: float = 0.3,
    max_chars: int = 32000,
    timeout: int = 300,
    use_cache: bool = False,
    cache_dir: str | None = None,
    on_progress: Optional[Callable[[int, int, int, Optional[str]], None]] = None,
) -> dict:
    """Generate LIVEWEB training data using real browser eval.

    Returns summary dict with counts and output path.
    """
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env", override=True)

    _ensure_playwright()
    _setup_path()
    model = model or _resolve_liveweb_llm()[0]
    resolved_base_url = base_url or _resolve_liveweb_llm()[1]
    resolved_api_key = api_key or _resolve_liveweb_llm()[2]
    normalized_base_url = _normalize_base_url(resolved_base_url)
    seed_values = list(seed_values or list(range(10000, 10010)))
    subtask_counts = list(subtasks or [1])
    selected_templates = _template_pool(include_plugins)

    print("LIVEWEB data generation")
    print(f"  Seeds: {seed_values[0]}-{seed_values[-1]} ({len(seed_values)})")
    print(f"  Subtasks: {subtask_counts}")
    if include_plugins:
        print(f"  Plugins: {include_plugins}")
    print(f"  Model: {model}")
    print(f"  Base URL: {normalized_base_url}")
    print(f"  Mode: {'cache' if use_cache else 'live'}")
    print(f"  Min score: {min_score}")
    print(f"  Output: {output}")

    from env import Actor

    actor = Actor(api_key=resolved_api_key, cache_dir=Path(cache_dir) if cache_dir else None, use_cache=use_cache)

    success = 0
    failed = 0
    filtered = 0
    errors = 0

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text("", encoding="utf-8")

    try:
        total = len(seed_values) * len(subtask_counts)
        completed = 0
        for seed in seed_values:
            for num_subtasks in subtask_counts:
                completed += 1
                rng = random.Random(seed * 31337 + num_subtasks)
                candidates = list(selected_templates)
                rng.shuffle(candidates)
                templates = candidates[:num_subtasks]
                print(f"[{completed}/{total}] seed={seed} subtasks={num_subtasks}", end=" ", flush=True)

                try:
                    result = await asyncio.wait_for(
                        actor.evaluate(
                            model=model,
                            base_url=normalized_base_url,
                            api_key=resolved_api_key,
                            seed=seed,
                            num_subtasks=num_subtasks,
                            templates=templates,
                            timeout=timeout,
                        ),
                        timeout=timeout + 120,
                    )

                    score = result.get("score", 0)
                    error = result.get("error")
                    conv = result.get("extra", {}).get("conversation", [])
                    total_chars = sum(len(str(m.get("content", "") or "")) for m in conv)

                    if error:
                        errors += 1
                        print(f"✗ error: {str(error)[:200]}")
                        if on_progress:
                            on_progress(seed, num_subtasks, 0, str(error))
                    elif score >= min_score and total_chars <= max_chars and conv:
                        record = {
                            "messages": conv,
                            "env": "LIVEWEB",
                            "source": "liveweb_eval",
                            "distill_model": model,
                            "score": score,
                            "seed": seed,
                            "num_subtasks": num_subtasks,
                        }
                        with open(output, "a", encoding="utf-8") as f:
                            f.write(json.dumps(record, ensure_ascii=False) + "\n")
                        success += 1
                        print(f"✓ score={score:.2f} msgs={len(conv)} ~{total_chars // 4}tok")
                        if on_progress:
                            on_progress(seed, num_subtasks, 1, None)
                    else:
                        filtered += 1
                        reason = f"score={score:.2f}" if score < min_score else f"~{total_chars // 4}tok"
                        print(f"✗ filtered ({reason})")
                        if on_progress:
                            on_progress(seed, num_subtasks, 0, reason)

                except asyncio.TimeoutError:
                    failed += 1
                    print("✗ timeout")
                    if on_progress:
                        on_progress(seed, num_subtasks, 0, "timeout")
                except Exception as e:
                    failed += 1
                    print(f"✗ {type(e).__name__}: {str(e)[:100]}")
                    if on_progress:
                        on_progress(seed, num_subtasks, 0, type(e).__name__)
    finally:
        await actor.shutdown()

    print(f"\n{'=' * 60}")
    print(f"Done: {success} success / {filtered} filtered / {failed} failed / {errors} errored")
    print(f"Output: {output}")

    return {
        "records": success,
        "success": success,
        "filtered": filtered,
        "failed": failed,
        "errors": errors,
        "output": output,
    }
