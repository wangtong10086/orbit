#!/usr/bin/env python3
"""Score NAVWORLD entries using Claude against actual eval rubric.

Uses Claude Haiku to evaluate each entry on 5 dimensions matching the actual
NAVWORLD LLM scorer: analysis_depth, factual_grounding, practicality, logic, user_experience.

Identifies low-quality entries for rewriting.
"""

import asyncio
import json
import os
import random
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

import anthropic

SCORING_PROMPT = """You are evaluating a Chinese travel planning assistant's response quality.

Score this travel plan on 5 dimensions (0-10 each):

1. **analysis_depth**: Does the plan provide reasoning and trade-off analysis, or just dump data?
   - 0-2: Pure data listing, no analysis
   - 5-6: Some reasoning but mostly listing
   - 7-8: Most sections have genuine analysis ("X is recommended because Y")
   - 9-10: Data-supported rationale with explicit trade-offs

2. **factual_grounding**: Does the plan cite specific data from tool results (POI names, flight numbers, prices, weather)?
   - Deduct for: transport numbers not from tools, prices without source, POIs not in search results
   - 10 = all claims grounded in tool data

3. **practicality**: Are logistics complete (transport modes, times, specific slots)?
   - Deduct for: missing transport details, no time slots, time conflicts

4. **logic**: Is the route geographically sensible? No unnecessary backtracking?
   - Deduct for: cross-district jumps, no ordering rationale

5. **user_experience**: Does it address user constraints (budget, preferences, group type)?
   - 9-10: All constraints addressed
   - 5-6: Core addressed, some ignored
   - 0-2: Template feel, ignores user needs

IMPORTANT: Score strictly. Most plans should be 5-6. 7+ is clearly above average. 9+ is rare.

Return ONLY a JSON object: {"analysis_depth": N, "factual_grounding": N, "practicality": N, "logic": N, "user_experience": N, "total": N, "weakest": "dimension_name", "note": "one sentence"}"""


def extract_plan_summary(entry: dict) -> str:
    """Extract user query + tool results summary + final plan from entry."""
    msgs = entry["messages"]
    parts = []

    # System prompt (abbreviated)
    parts.append("[System: Travel planning assistant with tools: poi_search, weather, direction, around_search, search_flights, search_train_tickets]")

    for m in msgs:
        role = m["role"]
        content = m.get("content", "")
        if role == "user":
            parts.append(f"[User]: {content[:500]}")
        elif role == "tool":
            parts.append(f"[Tool result]: {content[:300]}")
        elif role == "assistant" and "<tool_call>" in content:
            parts.append(f"[Assistant calls tools]: {content[:200]}")
        elif role == "assistant" and len(content) > 100:
            parts.append(f"[Final Plan]:\n{content}")

    return "\n\n".join(parts)


async def score_entry(client, entry_idx: int, entry: dict, semaphore) -> dict:
    """Score a single entry using Claude Haiku."""
    async with semaphore:
        summary = extract_plan_summary(entry)

        try:
            resp = await asyncio.to_thread(
                client.messages.create,
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                messages=[
                    {"role": "user", "content": f"{SCORING_PROMPT}\n\n---\n\n{summary}"}
                ],
            )
            text = resp.content[0].text.strip()
            # Parse JSON from response
            if "{" in text:
                json_str = text[text.index("{"):text.rindex("}") + 1]
                scores = json.loads(json_str)
                scores["entry_idx"] = entry_idx
                scores["input_tokens"] = resp.usage.input_tokens
                scores["output_tokens"] = resp.usage.output_tokens
                print(f"  [{entry_idx}] total={scores.get('total', '?')} weakest={scores.get('weakest', '?')}")
                return scores
            else:
                print(f"  [{entry_idx}] ERROR: no JSON in response")
                return {"entry_idx": entry_idx, "error": "no JSON", "raw": text[:200]}
        except Exception as e:
            print(f"  [{entry_idx}] ERROR: {e}")
            return {"entry_idx": entry_idx, "error": str(e)}


async def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    output = sys.argv[2] if len(sys.argv) > 2 else "data/navworld_scores.jsonl"

    client = anthropic.Anthropic(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        base_url=os.getenv("ANTHROPIC_BASE_URL"),
    )

    with open("data/canonical/navworld.jsonl") as f:
        entries = [json.loads(l) for l in f]

    # Sample n entries (stratified: some from original, some from D8, some from D9)
    random.seed(42)
    indices = random.sample(range(len(entries)), min(n, len(entries)))

    print(f"Scoring {len(indices)} NAVWORLD entries with Claude Haiku")
    print(f"Output: {output}")

    semaphore = asyncio.Semaphore(10)  # max 10 concurrent
    tasks = [score_entry(client, idx, entries[idx], semaphore) for idx in indices]
    results = await asyncio.gather(*tasks)

    # Write results
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Summary
    valid = [r for r in results if "total" in r]
    if valid:
        avg_total = sum(r["total"] for r in valid) / len(valid)
        totals = sorted(r["total"] for r in valid)
        bottom_20 = [r for r in valid if r["total"] <= totals[len(totals) // 5]]

        # Dimension averages
        dims = ["analysis_depth", "factual_grounding", "practicality", "logic", "user_experience"]
        print(f"\n{'='*60}")
        print(f"Scored {len(valid)}/{len(indices)} entries")
        print(f"Average total: {avg_total:.1f}/50")
        for d in dims:
            avg = sum(r.get(d, 0) for r in valid) / len(valid)
            print(f"  {d}: {avg:.1f}/10")
        print(f"Bottom 20% threshold: {totals[len(totals)//5]}")
        print(f"Bottom entries: {len(bottom_20)}")

        # Total cost
        total_input = sum(r.get("input_tokens", 0) for r in results)
        total_output = sum(r.get("output_tokens", 0) for r in results)
        print(f"Tokens: {total_input:,} input, {total_output:,} output")
        # Haiku pricing: ~$0.25/MTok input, ~$1.25/MTok output
        est_cost = total_input * 0.25 / 1e6 + total_output * 1.25 / 1e6
        print(f"Estimated cost: ~${est_cost:.3f}")


if __name__ == "__main__":
    asyncio.run(main())
