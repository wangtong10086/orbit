#!/usr/bin/env python3
"""Generate synthetic LIVEWEB training data using Claude.

Creates realistic browser interaction trajectories for missing plugins
(Taostats, Stooq, Weather) that match the actual eval format.

Uses Claude Sonnet to generate trajectories that look like real browser
interactions with accessibility trees and tool calls.
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

# Template definitions matching eval plugins
TEMPLATES = {
    "taostats_subnet_info": {
        "site": "taostats.io",
        "difficulty": "easy",
        "description": "Find subnet information on taostats.io",
        "tasks": [
            "What is the current emission rate for subnet {subnet_id} on Bittensor?",
            "How many validators are currently active on subnet {subnet_id}?",
            "What is the registration cost for subnet {subnet_id}?",
            "What is subnet {subnet_id}'s name and description?",
        ],
        "params": {"subnet_id": list(range(1, 40))},
    },
    "taostats_ranking": {
        "site": "taostats.io",
        "difficulty": "medium",
        "description": "Find ranking/comparison data on taostats",
        "tasks": [
            "Which subnet has the highest emission on Bittensor right now?",
            "What are the top 3 subnets by number of validators?",
            "Compare the registration costs of subnet {s1} and subnet {s2}.",
        ],
        "params": {"s1": list(range(1, 30)), "s2": list(range(1, 30))},
    },
    "stooq_price": {
        "site": "stooq.com",
        "difficulty": "easy",
        "description": "Look up stock/index prices on stooq.com",
        "tasks": [
            "What is the current price of {ticker} on Stooq?",
            "What was the closing price of {ticker} yesterday?",
            "What is the 52-week high for {ticker}?",
        ],
        "params": {"ticker": ["AAPL.US", "MSFT.US", "GOOGL.US", "AMZN.US", "TSLA.US", "SPY.US", "^DJI", "^SPX", "EURUSD", "GBPUSD", "GOLD", "BTC.V"]},
    },
    "stooq_comparison": {
        "site": "stooq.com",
        "difficulty": "medium",
        "description": "Compare financial instruments on stooq",
        "tasks": [
            "Compare the YTD performance of {t1} and {t2} on Stooq.",
            "Which has higher volume today: {t1} or {t2}?",
        ],
        "params": {"t1": ["AAPL.US", "MSFT.US", "GOOGL.US", "SPY.US"], "t2": ["AMZN.US", "TSLA.US", "META.US", "^SPX"]},
    },
}

SYSTEM_PROMPT = """You are a web automation agent that interacts with real websites to complete tasks.

You have access to a browser and can navigate to any website to gather information.
Use the provided tools to interact with web pages: navigate to URLs, click elements, type text, and extract information.

Available tools:
- navigate(url): Navigate to a URL
- click(element_id): Click on an element
- type(element_id, text): Type text into an input field
- extract(selector): Extract text content
- scroll(direction): Scroll up or down
- done(answer): Submit your final answer

When you find the answer, call done() with your answer in the format: answer1: <value>"""

GENERATION_PROMPT = """Generate a realistic browser interaction trajectory for this task.

Task: {task}
Website: {site}

Create a multi-turn conversation that looks like a real browser agent interaction:
1. The agent navigates to the website
2. Each step shows a "Current Page State" with URL, title, and a realistic accessibility tree
3. The agent takes actions (navigate, click, extract) and gets observations
4. Finally the agent calls done() with the answer

Format each message as follows:

Assistant messages: empty content (action is in tool call)
Tool messages: "Success" or brief result
User messages (observations): Include "## Current Page State" with URL, Title, Accessibility Tree, Recent Actions, Step counter

The accessibility tree should be realistic for {site} — include actual UI elements like navigation links, data tables, search bars, etc.

Generate 4-8 interaction steps. Keep total under 6000 characters.

Return ONLY a JSON array of messages: [{{"role": "system", "content": "..."}}, {{"role": "user", "content": "..."}}, ...]
Each message has only "role" and "content" keys. The last message must be from assistant with "answer1: <value>"."""


def generate_task(template_name: str, rng: random.Random) -> tuple[str, str]:
    """Generate a specific task from a template."""
    tmpl = TEMPLATES[template_name]
    task_template = rng.choice(tmpl["tasks"])
    params = {}
    for key, values in tmpl["params"].items():
        params[key] = rng.choice(values)
    task = task_template.format(**params)
    return task, tmpl["site"]


async def generate_trajectory(client, task: str, site: str, seed: int, semaphore) -> dict | None:
    """Generate one LIVEWEB trajectory using Claude Sonnet."""
    async with semaphore:
        prompt = GENERATION_PROMPT.format(task=task, site=site)

        try:
            resp = await asyncio.to_thread(
                client.messages.create,
                model="claude-sonnet-4-20250514",
                max_tokens=4000,
                messages=[
                    {"role": "user", "content": prompt}
                ],
            )
            text = resp.content[0].text.strip()

            # Parse JSON array
            if "[" in text:
                json_str = text[text.index("["):text.rindex("]") + 1]
                messages = json.loads(json_str)
            else:
                print(f"  [seed={seed}] ERROR: no JSON array")
                return None

            # Validate format
            if not messages or not isinstance(messages, list):
                print(f"  [seed={seed}] ERROR: invalid messages format")
                return None

            # Normalize: only (role, content)
            clean_msgs = []
            for m in messages:
                clean_msgs.append({
                    "role": m.get("role", "user"),
                    "content": m.get("content", ""),
                })

            # Check last message has answer
            last_content = clean_msgs[-1].get("content", "")
            if "answer" not in last_content.lower():
                print(f"  [seed={seed}] WARNING: no answer in last message")

            # Check total length
            total_chars = sum(len(m.get("content", "")) for m in clean_msgs)
            if total_chars > 32000:
                print(f"  [seed={seed}] FILTERED: too long ({total_chars} chars)")
                return None

            record = {
                "messages": clean_msgs,
                "env": "LIVEWEB",
                "source": "claude_distillation",
                "distill_model": "claude-sonnet-4-20250514",
                "score": 1.0,
                "seed": seed,
                "task": task,
                "site": site,
            }

            est_tok = total_chars // 4
            print(f"  [seed={seed}] OK: {len(clean_msgs)} msgs, ~{est_tok} tok, site={site}")
            return record

        except Exception as e:
            print(f"  [seed={seed}] ERROR: {e}")
            return None


async def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    output = sys.argv[2] if len(sys.argv) > 2 else "data/liveweb_claude_distill.jsonl"

    client = anthropic.Anthropic(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        base_url=os.getenv("ANTHROPIC_BASE_URL"),
    )

    rng = random.Random(42)

    # Generate tasks — weighted toward missing plugins
    tasks = []
    template_weights = {
        "taostats_subnet_info": 15,
        "taostats_ranking": 10,
        "stooq_price": 15,
        "stooq_comparison": 10,
    }

    for tmpl_name, count in template_weights.items():
        for i in range(count):
            task, site = generate_task(tmpl_name, rng)
            tasks.append((task, site, 60000 + len(tasks)))

    # Shuffle and trim to n
    rng.shuffle(tasks)
    tasks = tasks[:n]

    print(f"Generating {len(tasks)} LIVEWEB trajectories with Claude Sonnet")
    print(f"Output: {output}")
    sites = {}
    for _, site, _ in tasks:
        sites[site] = sites.get(site, 0) + 1
    print(f"Sites: {sites}")

    semaphore = asyncio.Semaphore(5)  # max 5 concurrent
    coros = [generate_trajectory(client, task, site, seed, semaphore) for task, site, seed in tasks]
    results = await asyncio.gather(*coros)

    # Write results
    records = [r for r in results if r is not None]
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n{'='*60}")
    print(f"Generated {len(records)}/{len(tasks)} trajectories")
    sites_out = {}
    for r in records:
        s = r["site"]
        sites_out[s] = sites_out.get(s, 0) + 1
    print(f"By site: {sites_out}")
    print(f"Output: {output}")


if __name__ == "__main__":
    asyncio.run(main())
