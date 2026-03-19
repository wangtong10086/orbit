"""LIVEWEB training data generator using real browser + Claude agent.

Runs liveweb-arena eval locally (no Docker needed) with Claude as the agent.
Captures full trajectories with tool_calls in correct eval format.

Usage via CLI:
    forge data liveweb-gen -n 10 --min-score 0.3 -o data/liveweb_claude.jsonl
"""

import asyncio
import json
import os
import sys
from pathlib import Path

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


async def generate_liveweb_data(
    count: int = 10,
    output: str = "data/liveweb_claude.jsonl",
    model: str = "claude-sonnet-4-20250514",
    min_score: float = 0.3,
    max_chars: int = 32000,
    start_seed: int = 10000,
    timeout: int = 300,
) -> dict:
    """Generate LIVEWEB training data using real browser eval.

    Returns summary dict with counts and output path.
    """
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env", override=True)

    _ensure_playwright()
    _setup_path()

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    base_url = os.getenv("ANTHROPIC_BASE_URL", "")

    # liveweb-arena uses OpenAI-compatible API format
    # Claude via proxy should work if the proxy supports OpenAI chat format
    # For now, set the keys that liveweb-arena expects
    os.environ["API_KEY"] = api_key
    os.environ.setdefault("API_BASE_URL", base_url + "/v1" if base_url else "")

    # Import liveweb-arena components
    from liveweb_arena.core.browser import BrowserEngine
    from liveweb_arena.core.task_manager import TaskManager
    from liveweb_arena.core.agent_protocol import FunctionCallingProtocol
    from liveweb_arena.core.agent_loop import AgentLoop
    from liveweb_arena.utils.llm_client import LLMClient

    print(f"LIVEWEB data generation")
    print(f"  Count: {count}")
    print(f"  Model: {model}")
    print(f"  Min score: {min_score}")
    print(f"  Output: {output}")

    # Use the env.py Actor directly for simpler integration
    from env import Actor

    actor = Actor()

    success = 0
    failed = 0
    filtered = 0

    Path(output).parent.mkdir(parents=True, exist_ok=True)

    for i in range(count):
        seed = start_seed + i
        print(f"[{i+1}/{count}] seed={seed}", end=" ", flush=True)

        try:
            result = await asyncio.wait_for(
                actor.evaluate(
                    model=model,
                    base_url=base_url + "/v1" if base_url and not base_url.endswith("/v1") else base_url,
                    seed=seed,
                    num_subtasks=1,
                    timeout=timeout,
                ),
                timeout=timeout + 120,
            )

            score = result.get("score", 0)
            error = result.get("error")
            conv = result.get("extra", {}).get("conversation", [])
            total_chars = sum(len(str(m.get("content", "") or "")) for m in conv)

            if error:
                failed += 1
                print(f"✗ error: {str(error)[:300]}")
            elif score >= min_score and total_chars <= max_chars:
                record = {
                    "messages": conv,
                    "env": "LIVEWEB",
                    "source": "claude_real_eval",
                    "distill_model": model,
                    "score": score,
                    "seed": seed,
                }
                with open(output, "a") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                success += 1
                print(f"✓ score={score:.2f} msgs={len(conv)} ~{total_chars // 4}tok")
            else:
                filtered += 1
                reason = f"score={score:.2f}" if score < min_score else f"~{total_chars // 4}tok"
                print(f"✗ filtered ({reason})")

        except asyncio.TimeoutError:
            failed += 1
            print("✗ timeout")
        except Exception as e:
            failed += 1
            print(f"✗ {type(e).__name__}: {str(e)[:100]}")

    print(f"\n{'=' * 60}")
    print(f"Done: {success} success / {filtered} filtered / {failed} failed")
    print(f"Output: {output}")

    return {"success": success, "filtered": filtered, "failed": failed, "output": output}
