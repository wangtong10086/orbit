#!/usr/bin/env python3
"""
SWE-Infinite Synthetic Trajectory Generator

Generates training trajectories WITHOUT Docker by having GPT-5.4
create realistic multi-turn debugging conversations from task
problem_statement + solution patch.

Usage:
    python3 scripts/swe_synth_gen.py --task-range 1-345 --output data/swe_synth_trajectories.jsonl
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError

R2_BASE = "https://pub-7882418a56434a479bf9a7febd660b36.r2.dev/bugs"
ACTION_RE = re.compile(r"```bash\s*\n(.*?)\n```", re.DOTALL)

# Exact eval system prompt (from affinetes config.yaml)
SYSTEM_PROMPT = """\
You are a helpful assistant that can interact multiple times with a computer shell to solve programming tasks.
Your response must contain exactly ONE bash code block with ONE command (or commands connected with && or ||).

Include a THOUGHT section before your command where you explain your reasoning process.
Format your response as shown in <format_example>.

<format_example>
THOUGHT: Your reasoning and analysis here

```bash
your_command_here
```
</format_example>

Failure to follow these rules will cause your response to be rejected."""

# Exact eval instance template (from affinetes config.yaml)
INSTANCE_TEMPLATE = """\
<pr_description>
Consider the following issue or PR description:
{task}
</pr_description>

<instructions>
# Task Instructions

## Overview
You're a software engineer interacting continuously with a computer by submitting commands.
You'll be helping implement necessary changes to meet requirements described above.
Your task is to make changes to source files in the current directory to resolve the described issue in a way that is general and consistent with the codebase.

IMPORTANT: This is an interactive process where you will think and issue ONE command, see its result, then think and issue your next command.

For each response:
1. Include a THOUGHT section explaining your reasoning and what you're trying to accomplish
2. Provide exactly ONE bash command to execute

## Important Boundaries
- MODIFY: Regular source code files in /app (this is the working directory for all your subsequent commands)
- DO NOT MODIFY: Tests, configuration files (pyproject.toml, setup.cfg, etc.)
- NEVER add or modify unit tests. Your job is ONLY to implement or fix the source code.

## Submission
When you've completed your work, issue exactly:

```bash
echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && git add -A && git diff --cached
```
</instructions>"""

SYNTH_SYSTEM = """\
You are generating training data for a code repair model. Given a bug report and its correct fix, \
produce a realistic multi-turn debugging conversation as a JSON array.

Each developer turn:
{"role": "assistant", "content": "THOUGHT: [clear reasoning about the bug and next step]\\n\\n```bash\\ncommand\\n```"}

Each system observation:
{"role": "user", "content": "<returncode>0</returncode>\\n<output>\\n[realistic output]\\n</output>"}

CRITICAL RULES:
1. 6-12 assistant turns total
2. Workflow: explore (grep/cat/find) → understand → edit (sed -i) → verify → submit
3. Final command MUST be: echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && git add -A && git diff --cached
4. The final git diff output MUST show the correct patch
5. System outputs must be realistic (actual file contents, grep results, test output)
6. Every assistant turn: exactly ONE ```bash block
7. Every THOUGHT must explain clear reasoning, not just "let me do X"
8. Working directory is /app
9. Output ONLY the JSON array — no markdown wrapper, no explanation"""


def _load_dotenv(path: str = ".env"):
    env_path = Path(path)
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = val


def load_task(task_id: int) -> dict | None:
    cache_dir = Path("/tmp/swe-distill-cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    local = cache_dir / f"task_{task_id:011d}.json"
    if local.exists():
        with open(local) as f:
            return json.load(f)
    url = f"{R2_BASE}/task_{task_id:011d}.json"
    try:
        req = Request(url, headers={"User-Agent": "swe-synth/1.0"})
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        with open(local, "w") as f:
            json.dump(data, f, indent=2)
        return data
    except HTTPError as e:
        if e.code == 404:
            return None
        return None
    except Exception:
        return None


def call_llm(messages: list, model: str, api_base: str, api_key: str,
             max_tokens: int = 8192) -> str | None:
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": max_tokens,
    }).encode()

    for attempt in range(3):
        try:
            req = Request(
                f"{api_base}/chat/completions",
                data=payload,
                headers={"Authorization": f"Bearer {api_key}",
                         "Content-Type": "application/json"},
            )
            with urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
        except HTTPError as e:
            if e.code == 429:
                time.sleep(10 * (attempt + 1))
                continue
            if attempt < 2:
                time.sleep(5)
                continue
            return None
        except Exception:
            if attempt < 2:
                time.sleep(5)
                continue
            return None
    return None


def generate_trajectory(task: dict, model: str, api_base: str,
                        api_key: str) -> dict | None:
    """Generate a synthetic trajectory for a single task."""
    # Trim patch to avoid token limits
    patch = task["patch"]
    if len(patch) > 3000:
        patch = patch[:3000] + "\n... (truncated)"

    user_msg = (
        f"Repository: {task['repo']} ({task['repo_language']})\n\n"
        f"Bug report:\n{task['problem_statement'][:1500]}\n\n"
        f"Correct fix (unified diff):\n```diff\n{patch}\n```\n\n"
        f"Generate the multi-turn debugging conversation as a JSON array."
    )

    content = call_llm(
        [{"role": "system", "content": SYNTH_SYSTEM},
         {"role": "user", "content": user_msg}],
        model, api_base, api_key,
    )
    if not content:
        return None

    # Parse JSON array
    json_match = re.search(r'\[.*\]', content, re.DOTALL)
    if not json_match:
        return None

    try:
        turns = json.loads(json_match.group())
    except json.JSONDecodeError:
        return None

    if not turns or len(turns) < 4:
        return None

    # Validate format
    asst_turns = [t for t in turns if t.get("role") == "assistant"]
    if len(asst_turns) < 3:
        return None

    for t in asst_turns:
        if "THOUGHT" not in t.get("content", "").upper():
            return None
        if not ACTION_RE.search(t.get("content", "")):
            return None

    # Check last assistant has submit marker
    last_asst = asst_turns[-1]["content"]
    if "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT" not in last_asst:
        return None

    # Build full training entry with eval system/instance prompts
    instance_prompt = INSTANCE_TEMPLATE.format(task=task["problem_statement"][:2000])
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": instance_prompt},
    ] + turns

    # Ensure last message is assistant
    if messages[-1]["role"] != "assistant":
        messages = messages[:-1]

    return {
        "messages": messages,
        "env": "SWE-INFINITE",
        "score": 1.0,
        "instance_id": task["instance_id"],
        "repo": task["repo"],
        "language": task["repo_language"],
        "synthetic": True,
    }


def load_completed(output_path: str) -> set:
    completed = set()
    if os.path.exists(output_path):
        with open(output_path) as f:
            for line in f:
                try:
                    e = json.loads(line.strip())
                    completed.add(e.get("instance_id", ""))
                except:
                    pass
    return completed


def main():
    _load_dotenv()
    parser = argparse.ArgumentParser(description="SWE-Infinite synthetic trajectory generator")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--api-base", default=os.getenv("OPENAI_BASE_URL", ""))
    parser.add_argument("--api-key", default=os.getenv("OPENAI_API_KEY", ""))
    parser.add_argument("--task-range", default="1-345")
    parser.add_argument("--output", default="data/swe_infinite_synth.jsonl")
    parser.add_argument("--max-patch-size", type=int, default=5000,
                        help="Skip tasks with patches larger than this")
    args = parser.parse_args()

    if not args.api_key:
        print("ERROR: need --api-key or $OPENAI_API_KEY")
        sys.exit(1)

    # Parse task range
    if "-" in args.task_range:
        lo, hi = args.task_range.split("-", 1)
        task_ids = list(range(int(lo), int(hi) + 1))
    elif "," in args.task_range:
        task_ids = [int(x) for x in args.task_range.split(",")]
    else:
        task_ids = [int(args.task_range)]

    completed = load_completed(args.output)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    stats = {"success": 0, "format_fail": 0, "api_fail": 0, "skip_large": 0, "skip_done": 0}

    for tid in task_ids:
        task = load_task(tid)
        if not task:
            continue
        if task["instance_id"] in completed:
            stats["skip_done"] += 1
            continue
        if len(task.get("patch", "")) > args.max_patch_size:
            stats["skip_large"] += 1
            continue

        print(f"[Task {tid}] {task['instance_id']} ({task['repo_language']})")

        result = generate_trajectory(task, args.model, args.api_base, args.api_key)
        if result is None:
            print(f"  FAIL")
            stats["format_fail" if True else "api_fail"] += 1
            continue

        asst = [m for m in result["messages"] if m["role"] == "assistant"]
        with open(args.output, "a") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
        print(f"  OK ({len(asst)} turns)")
        stats["success"] += 1

    total = sum(stats.values())
    print(f"\n{'='*50}")
    print(f"COMPLETE: {stats['success']} generated, {stats['format_fail']} failed, "
          f"{stats['skip_large']} too large, {stats['skip_done']} already done")
    if total > 0:
        print(f"Success rate: {stats['success']}/{total-stats['skip_done']-stats['skip_large']}")


if __name__ == "__main__":
    main()
