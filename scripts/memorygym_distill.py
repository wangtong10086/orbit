#!/usr/bin/env python3
"""MemoryGym distillation via strong models (GPT-5.4 etc).

Runs bench.py with a patched system prompt that enforces <tool_call> format
for models that don't naturally produce it (GPT-5.4, Claude, etc).

Usage:
    # Single seed pilot
    python scripts/memorygym_distill.py --model gpt-5.4 --seed 0 --template company --tier lite

    # Batch distillation (10 templates × 5 seeds = 50 trajectories)
    python scripts/memorygym_distill.py --model gpt-5.4 --seeds 5 --tier lite
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Add pylibs and MemoryGym to path
PYLIBS = Path(__file__).parent.parent / ".pylibs"
MEMORYGYM = Path(__file__).parent.parent / "repos" / "MemoryGym"
sys.path.insert(0, str(PYLIBS))
sys.path.insert(0, str(MEMORYGYM))

# Set cache dir before any imports
CACHE_DIR = Path(__file__).parent.parent / ".cache" / "huggingface"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ["HF_HOME"] = str(CACHE_DIR)
os.environ["TRANSFORMERS_CACHE"] = str(CACHE_DIR)
os.environ["SENTENCE_TRANSFORMERS_HOME"] = str(CACHE_DIR)

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")


# Stronger system prompt with few-shot examples for each event type
DISTILL_SYSTEM_PROMPT = """You are participating in a memory management evaluation.
Write budget: {budget} total writes. Be selective — you'll see more entities than you can store.

## Tools — MANDATORY FORMAT

You MUST call tools using EXACTLY this XML format. No plain text descriptions.

**Write** — Store entity data (costs 1 write):
<tool_call>{{"name": "Write", "arguments": {{"content": "EntityName | key: value | key: value"}}}}</tool_call>

**Edit** — Update memory (free during corrections):
<tool_call>{{"name": "Edit", "arguments": {{"old_text": "old value", "new_text": "new value"}}}}</tool_call>

**memory_search** — Search memory (free):
<tool_call>{{"name": "memory_search", "arguments": {{"query": "entity name"}}}}</tool_call>

**submit_answer** — Submit answer:
<tool_call>{{"name": "submit_answer", "arguments": {{"answer": "your answer"}}}}</tool_call>

## Examples

### DOCUMENTS event → Write each important entity:
<tool_call>{{"name": "Write", "arguments": {{"content": "Acme Corp | Revenue: $500M | Founded: 1995 | Employees: 2000"}}}}</tool_call>
<tool_call>{{"name": "Write", "arguments": {{"content": "Beta Inc | Revenue: $200M | Founded: 2001 | CEO tenure: 5 years"}}}}</tool_call>

### CORRECTION event → Search then Edit:
<tool_call>{{"name": "memory_search", "arguments": {{"query": "Acme Corp"}}}}</tool_call>
(after seeing search results showing "Revenue: $500M")
<tool_call>{{"name": "Edit", "arguments": {{"old_text": "Revenue: $500M", "new_text": "Revenue: $600M"}}}}</tool_call>

### QUESTION event → Search then Answer:
<tool_call>{{"name": "memory_search", "arguments": {{"query": "Acme Corp"}}}}</tool_call>
(after seeing search results showing "Revenue: $600M")
<tool_call>{{"name": "submit_answer", "arguments": {{"answer": "$600M"}}}}</tool_call>

## CRITICAL RULES
1. DOCUMENTS: Output <tool_call> Write for each entity to store. One Write per entity. Be selective with budget.
2. CORRECTIONS: ALWAYS call memory_search first, then Edit with old_text/new_text. Never just describe the update.
3. QUESTIONS: ALWAYS call memory_search first, read the results, then submit_answer with the exact value.
4. If entity not in memory: submit "I don't have enough information"
5. NEVER output plain text descriptions of actions. ONLY use <tool_call> tags.
"""


def patch_and_run(model: str, seed: int, template: str, tier: str,
                  api_base: str | None, quiet: bool) -> dict | None:
    """Run bench with patched system prompt."""
    import memorygym.agents.stream_agent as agent_mod

    # Monkey-patch the system prompt
    original_prompt = agent_mod.SYSTEM_PROMPT
    agent_mod.SYSTEM_PROMPT = DISTILL_SYSTEM_PROMPT

    try:
        from memorygym.bench import main as bench_main
        exit_code = bench_main([
            "--model", model,
            "--seed", str(seed),
            "--template", template,
            "--tier", tier,
            *(["--api-base", api_base] if api_base else []),
            *(["--quiet"] if quiet else []),
        ])
        return {"exit_code": exit_code}
    finally:
        agent_mod.SYSTEM_PROMPT = original_prompt


def main():
    parser = argparse.ArgumentParser(description="MemoryGym distillation")
    parser.add_argument("--model", "-m", default="gpt-5.4")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--seeds", type=int, default=1)
    parser.add_argument("--template", "-t", default=None,
                        help="Template (default: all)")
    parser.add_argument("--tier", default="lite",
                        choices=["lite", "standard", "hard"])
    parser.add_argument("--api-base", default=None,
                        help="API base URL (auto-detected from env)")
    parser.add_argument("--quiet", "-q", action="store_true")
    args = parser.parse_args()

    # Auto-detect API base
    api_base = args.api_base or os.environ.get("OPENAI_BASE_URL") or os.environ.get("API_URL")

    from memorygym.simulation import TEMPLATES
    templates = [args.template] if args.template else list(TEMPLATES.keys())
    seeds = [args.seed] if args.seed is not None else list(range(args.seeds))

    total = len(templates) * len(seeds)
    done = 0

    for tmpl in templates:
        for seed in seeds:
            done += 1
            print(f"\n{'='*60}")
            print(f"[{done}/{total}] {tmpl} seed={seed}")
            print(f"{'='*60}")
            patch_and_run(
                model=args.model,
                seed=seed,
                template=tmpl,
                tier=args.tier,
                api_base=api_base,
                quiet=args.quiet,
            )

    print(f"\nDone. {done} trajectories saved to eval/")


if __name__ == "__main__":
    main()
