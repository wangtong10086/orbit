#!/usr/bin/env python3
"""
SWE-Infinite Trajectory Distillation

Runs a strong teacher model (GPT-5.4 / Claude) against SWE-Infinite tasks
stored in R2, collects successful fix trajectories, and exports them as
training data for Qwen3-32B.

Usage:
    source .env
    python3 scripts/swe_distill.py \
        --model gpt-5.4 \
        --api-base $OPENAI_BASE_URL \
        --api-key $OPENAI_API_KEY \
        --task-range 1-345 \
        --output data/swe_infinite_trajectories.jsonl \
        --workers 2

Architecture: Pure API calls + docker exec (no external deps beyond requests).
Reference: repos/affine-swe-infinite/src/augmenters/codex_augmenter.py
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import HTTPError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

R2_BASE = "https://pub-7882418a56434a479bf9a7febd660b36.r2.dev/bugs"
SUBMIT_MARKER = "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"
ACTION_RE = re.compile(r"```bash\s*\n(.*?)\n```", re.DOTALL)
MAX_STEPS = 50
MAX_WALL_TIME = 600  # 10 minutes
MAX_OUTPUT_CHARS = 10000
DOCKER_EXEC_TIMEOUT = 120
CONTAINER_MEMORY = "4g"

# Git sanitization script (from affinetes utils.py — strips history to prevent cheating)
SANITIZE_GIT = (
    "cd /app && "
    "git config user.email 'dev@test.local' && "
    "git config user.name 'Developer' && "
    "git checkout -- . 2>/dev/null; "
    "git clean -fd 2>/dev/null; "
    "git log --oneline -1"
)

# System prompt — exact copy from affinetes/environments/SWE-INFINITE/agents/config.yaml
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

## Recommended Workflow
1. Analyze the codebase by finding and reading relevant files
2. Create a simple script to reproduce the issue
3. Edit the source code to resolve the issue
4. Verify your fix works by running your script again
5. Submit your changes and finish your work by issuing the following command: `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && git add -A && git diff --cached`
   Do not combine it with any other command. <important>After this command, you cannot continue working on this task.</important>

## Command Execution Rules
You are operating in an environment where
1. You write a single command
2. The system executes that command in a subshell
3. You see the result
4. You write your next command

Each response should include:
1. A **THOUGHT** section where you explain your reasoning and plan
2. A single bash code block with your command

Format your responses like this:

<format_example>
THOUGHT: Here I explain my reasoning process, analysis of the current situation,
and what I'm trying to accomplish with the command below.

```bash
your_command_here
```
</format_example>

Commands must be specified in a single bash code block:

```bash
your_command_here
```

**CRITICAL REQUIREMENTS:**
- Your response SHOULD include a THOUGHT section explaining your reasoning
- Your response MUST include EXACTLY ONE bash code block
- This bash block MUST contain EXACTLY ONE command (or a set of commands connected with && or ||)
- If you include zero or multiple bash blocks, or no command at all, YOUR RESPONSE WILL FAIL
- Do NOT try to run multiple independent commands in separate blocks in one response
- Directory or environment variable changes are not persistent. Every action is executed in a new subshell.
- However, you can prefix any action with `MY_ENV_VAR=MY_VALUE cd /path/to/working/dir && ...` or write/load environment variables from files

Example of a CORRECT response:
<example_response>
THOUGHT: I need to understand the structure of the repository first. Let me check what files are in the current directory to get a better understanding of the codebase.

```bash
ls -la
```
</example_response>

Example of an INCORRECT response:
<example_response>
THOUGHT: I need to examine the codebase and then look at a specific file. I'll run multiple commands to do this.

```bash
ls -la
```

Now I'll read the file:

```bash
cat file.txt
```
</example_response>

If you need to run multiple commands, either:
1. Combine them in one block using && or ||
```bash
command1 && command2 || echo "Error occurred"
```

2. Wait for the first command to complete, see its output, then issue the next command in your following response.

## Environment Details
- You have a full Linux shell environment
- Always use non-interactive flags (-y, -f) for commands
- Avoid interactive tools like vi, nano, or any that require user input
- If a command isn't available, you can install it

## Useful Command Examples

### Create a new file:
```bash
cat <<'EOF' > newfile.py
import numpy as np
hello = "world"
print(hello)
EOF
```

### Edit files with sed:
```bash
# Replace all occurrences
sed -i 's/old_string/new_string/g' filename.py

# Replace only first occurrence
sed -i 's/old_string/new_string/' filename.py

# Replace first occurrence on line 1
sed -i '1s/old_string/new_string/' filename.py

# Replace all occurrences in lines 1-10
sed -i '1,10s/old_string/new_string/g' filename.py
```

### View file content:
```bash
# View specific lines with numbers
nl -ba filename.py | sed -n '10,20p'
```

### Any other command you want to run
```bash
anything
```

## Submission
When you've completed your work (reading, editing, testing), and cannot make further progress
issue exactly the following command:

```bash
echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && git add -A && git diff --cached
```

This command will submit your work.
You cannot continue working (reading, editing, testing) in any way on this task after submitting.
</instructions>"""


# ---------------------------------------------------------------------------
# Task Loading (R2 two-level cache)
# ---------------------------------------------------------------------------

def load_task(task_id: int, cache_dir: str = "/tmp/swe-distill-cache") -> Optional[dict]:
    """Load task from local cache or R2 public bucket."""
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)
    local = cache_path / f"task_{task_id:011d}.json"

    if local.exists():
        with open(local) as f:
            return json.load(f)

    url = f"{R2_BASE}/task_{task_id:011d}.json"
    try:
        req = Request(url, headers={"User-Agent": "swe-distill/1.0"})
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        with open(local, "w") as f:
            json.dump(data, f, indent=2)
        return data
    except HTTPError as e:
        if e.code == 404:
            return None
        print(f"  [WARN] R2 error for task {task_id}: {e.code}")
        return None
    except Exception as e:
        print(f"  [WARN] R2 fetch error for task {task_id}: {e}")
        return None


# ---------------------------------------------------------------------------
# Docker helpers
# ---------------------------------------------------------------------------

def docker_exec(container: str, cmd: str, timeout: int = DOCKER_EXEC_TIMEOUT) -> tuple[str, int]:
    """Execute command in container. Returns (output, exit_code)."""
    r = subprocess.run(
        ["docker", "exec", container, "bash", "-c", cmd],
        capture_output=True, encoding="utf-8", errors="replace", timeout=timeout,
    )
    out = r.stdout
    if r.stderr:
        out = f"{out}\n{r.stderr}" if out else r.stderr
    return out.strip(), r.returncode


LANG_BASE_IMAGES = {
    "go": "golang:1.22",
    "rust": "rust:1.83",
    "python": "python:3.11-slim",
    "ruby": "ruby:3.2-slim",
    "javascript": "node:20-slim",
}


def build_local_image(task: dict) -> Optional[str]:
    """Build Docker image locally from repo + base_commit. Returns image tag or None."""
    repo = task.get("repo", "")
    commit = task.get("base_commit", "")
    lang = task.get("repo_language", "")
    if not repo or not commit:
        return None

    tag = f"swe-local:{repo.replace('/', '.')}-{commit[:8]}"

    # Check if already built
    inspect = subprocess.run(
        ["docker", "image", "inspect", tag],
        capture_output=True, timeout=10,
    )
    if inspect.returncode == 0:
        print(f"  [LOCAL] Reusing {tag}")
        return tag

    base = LANG_BASE_IMAGES.get(lang, "ubuntu:22.04")

    # Check if base image is cached locally — try GCR mirror if not
    base_check = subprocess.run(
        ["docker", "image", "inspect", base],
        capture_output=True, timeout=10,
    )
    if base_check.returncode != 0:
        # Try Google Container Registry mirror (no rate limit)
        gcr_image = f"mirror.gcr.io/library/{base}"
        print(f"  [LOCAL] Base image {base} not cached — trying GCR mirror...")
        gcr_pull = subprocess.run(
            ["docker", "pull", gcr_image],
            capture_output=True, text=True, timeout=300,
        )
        if gcr_pull.returncode == 0:
            subprocess.run(["docker", "tag", gcr_image, base],
                           capture_output=True, timeout=10)
            print(f"  [LOCAL] Restored {base} from GCR mirror")
        else:
            print(f"  [LOCAL] Base image {base} not available (DockerHub+GCR both failed)")
            return None

    install_cmd = {
        "go": "cd /app && go mod download 2>/dev/null || true",
        "rust": "cd /app && cargo fetch 2>/dev/null || true",
        "python": "cd /app && pip install -e '.[dev,test]' 2>/dev/null || pip install -e . 2>/dev/null || true",
        "ruby": "cd /app && bundle install 2>/dev/null || true",
        "javascript": "cd /app && npm install 2>/dev/null || yarn install 2>/dev/null || true",
    }.get(lang, "true")

    dockerfile = (
        f"FROM {base}\n"
        f"RUN apt-get update && apt-get install -y git curl && rm -rf /var/lib/apt/lists/*\n"
        f"RUN git clone https://github.com/{repo}.git /app\n"
        f"WORKDIR /app\n"
        f"RUN git checkout {commit}\n"
        f"RUN {install_cmd}\n"
    )

    print(f"  [LOCAL] Building {tag} ({lang}, {base})...")
    r = subprocess.run(
        ["docker", "build", "-t", tag, "-f", "-", "."],
        input=dockerfile, capture_output=True, text=True, timeout=600,
    )
    if r.returncode != 0:
        err = r.stderr[-200:] if r.stderr else "unknown"
        print(f"  [LOCAL] Build failed: {err}")
        return None

    print(f"  [LOCAL] Built {tag}")
    return tag


_local_only = False  # Set via --local-only flag to skip DockerHub pulls


def start_container(image: str, task: dict = None) -> Optional[str]:
    """Pull/build image and start detached container. Returns container name or None."""
    name = f"swe-distill-{uuid.uuid4().hex[:12]}"

    pulled = False
    if not _local_only:
        # Try pull first
        pull = subprocess.run(
            ["docker", "pull", image],
            capture_output=True, text=True, timeout=300,
        )
        pulled = pull.returncode == 0

    if not pulled:
        # Check if local
        inspect = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True, timeout=10,
        )
        if inspect.returncode != 0:
            # Try local build
            if task:
                local_tag = build_local_image(task)
                if local_tag:
                    image = local_tag
                else:
                    print(f"  [ERROR] Cannot pull or build: {image}")
                    return None
            else:
                print(f"  [ERROR] Cannot pull image: {image}")
                return None

    # Start container
    r = subprocess.run(
        ["docker", "run", "-d", "--name", name,
         "--memory", CONTAINER_MEMORY, "--workdir", "/app",
         "--entrypoint", "",
         image, "sleep", "1800"],
        capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        print(f"  [ERROR] Container start failed: {r.stderr.strip()}")
        return None

    # Sanitize git
    docker_exec(name, SANITIZE_GIT, timeout=60)
    return name


def stop_container(name: str):
    """Force-remove container."""
    try:
        subprocess.run(["docker", "rm", "-f", name],
                       capture_output=True, timeout=30)
    except Exception:
        pass


_prune_counter = 0


def maybe_prune_images(force: bool = False):
    """Prune swe-local Docker images every 10 tasks to prevent disk fill.

    Only removes swe-local:* images (built by us). Never touches base images
    (golang, python, rust, ruby, node) or affinefoundation images.
    """
    global _prune_counter
    _prune_counter += 1
    if not force and _prune_counter % 10 != 0:
        return
    try:
        # Only remove swe-local images, not base images
        r = subprocess.run(
            ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}", "--filter", "reference=swe-local:*"],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode == 0 and r.stdout.strip():
            images = r.stdout.strip().split("\n")
            if len(images) > 5:  # keep some recent ones
                to_remove = images[5:]  # remove oldest (docker lists newest first)
                subprocess.run(
                    ["docker", "rmi", "-f"] + to_remove,
                    capture_output=True, timeout=120,
                )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# LLM API
# ---------------------------------------------------------------------------

def call_llm(
    messages: list[dict],
    model: str,
    api_base: str,
    api_key: str,
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> Optional[str]:
    """Call OpenAI-compatible chat API with streaming. Returns assistant content or None."""
    import urllib.request
    url = f"{api_base}/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }).encode()

    for attempt in range(15):
        try:
            req = Request(
                url, data=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            with urlopen(req, timeout=1800) as resp:
                content_parts = []
                for raw_line in resp:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line or line == "data: [DONE]":
                        continue
                    if line.startswith("data: "):
                        try:
                            chunk = json.loads(line[6:])
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            if "content" in delta and delta["content"]:
                                content_parts.append(delta["content"])
                        except (json.JSONDecodeError, IndexError, KeyError):
                            pass
                result = "".join(content_parts)
                return result if result else None
        except HTTPError as e:
            body = e.read().decode(errors="replace")[:500]
            if e.code in (429, 500, 502, 503, 504, 520, 522, 524, 525):
                wait = min(120, 15 * (attempt + 1))
                print(f"  [API_{e.code}] Retry {attempt+1}/15 in {wait}s")
                time.sleep(wait)
                continue
            print(f"  [API_ERROR] {e.code}: {body[:200]}")
            if attempt < 14:
                time.sleep(15)
                continue
            return None
        except Exception as e:
            print(f"  [API_ERROR] {e}")
            if attempt < 14:
                wait = min(120, 15 * (attempt + 1))
                time.sleep(wait)
                continue
            return None
    return None


# ---------------------------------------------------------------------------
# Observation formatting (matches config.yaml action_observation_template)
# ---------------------------------------------------------------------------

def format_observation(output: str, returncode: int) -> str:
    """Format command output as observation message for the agent."""
    if len(output) < MAX_OUTPUT_CHARS:
        return f"<returncode>{returncode}</returncode>\n<output>\n{output}\n</output>"

    elided = len(output) - MAX_OUTPUT_CHARS
    return (
        f"<returncode>{returncode}</returncode>\n"
        f"<warning>\n"
        f"The output of your last command was too long.\n"
        f"Please try a different command that produces less output.\n"
        f"</warning>\n"
        f"<output_head>\n{output[:5000]}\n</output_head>\n"
        f"<elided_chars>\n{elided} characters elided\n</elided_chars>\n"
        f"<output_tail>\n{output[-5000:]}\n</output_tail>"
    )


# ---------------------------------------------------------------------------
# Agent Loop
# ---------------------------------------------------------------------------

def run_agent(
    task: dict,
    model: str,
    api_base: str,
    api_key: str,
    dry_run: bool = False,
) -> Optional[dict]:
    """
    Run teacher model against a single SWE task.

    Returns dict with keys: messages, patch, score, instance_id, repo,
    language, turns, wall_time. Returns None on infrastructure failure.

    If dry_run=True, simulates Docker execution (for testing without Docker).
    """
    image = task["dockerhub_tag"]
    problem = task["problem_statement"]
    instance_id = task["instance_id"]
    language = task.get("repo_language", "unknown")

    print(f"  [{instance_id}] Starting ({language}, image={image.split('/')[-1][:40]})")

    container = None
    if not dry_run:
        container = start_container(image, task=task)
        if not container:
            return None

    def exec_cmd(cmd: str, timeout: int = DOCKER_EXEC_TIMEOUT) -> tuple[str, int]:
        if dry_run:
            if SUBMIT_MARKER in cmd:
                return f"{SUBMIT_MARKER}\ndiff --git a/file.py b/file.py\n--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new", 0
            return f"(dry-run: would execute: {cmd[:80]})", 0
        return docker_exec(container, cmd, timeout)

    try:
        # Build initial messages
        user_prompt = INSTANCE_TEMPLATE.format(task=problem)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        wall_start = time.time()
        format_errors = 0
        last_output = ""
        max_steps = 3 if dry_run else MAX_STEPS

        for step in range(max_steps):
            elapsed = time.time() - wall_start
            if not dry_run and elapsed > MAX_WALL_TIME:
                print(f"  [{instance_id}] Wall-clock timeout at step {step}")
                break

            # Call LLM
            content = call_llm(messages, model, api_base, api_key)
            if content is None:
                print(f"  [{instance_id}] LLM call failed at step {step}")
                break

            # Strip think tags if present
            if "</think>" in content:
                content = content.split("</think>")[-1].strip()

            messages.append({"role": "assistant", "content": content})

            # Extract bash command
            actions = ACTION_RE.findall(content)
            if len(actions) != 1:
                format_errors += 1
                if format_errors >= 3:
                    print(f"  [{instance_id}] Too many format errors, stopping")
                    break
                # Send format error as observation
                err_msg = (
                    f"Please always provide EXACTLY ONE action in triple backticks, "
                    f"found {len(actions)} actions.\n\n"
                    f"Format your response with a THOUGHT section followed by exactly "
                    f"one ```bash ... ``` block."
                )
                messages.append({"role": "user", "content": err_msg})
                continue

            format_errors = 0
            command = actions[0].strip()

            # Check for submission
            if SUBMIT_MARKER in command:
                # Reject premature submissions — model must explore first
                if step < 3 and not dry_run:
                    reject_msg = (
                        "<returncode>1</returncode>\n<output>\n"
                        "ERROR: You have not made any changes yet. "
                        "Please first:\n"
                        "1. Explore the codebase to understand the structure\n"
                        "2. Find the relevant files to modify\n"
                        "3. Make your code changes\n"
                        "4. Verify your changes work\n"
                        "Then submit.\n</output>"
                    )
                    messages.append({"role": "user", "content": reject_msg})
                    print(f"  [{instance_id}] Rejected premature submit at step {step}")
                    continue

                try:
                    output, rc = exec_cmd(command, timeout=60)
                except subprocess.TimeoutExpired:
                    output, rc = "(command timed out)", 1
                last_output = output
                messages.append({"role": "user", "content": format_observation(output, rc)})
                print(f"  [{instance_id}] Submitted at step {step} ({elapsed:.0f}s)")
                break

            # Execute command
            try:
                output, rc = exec_cmd(command)
            except subprocess.TimeoutExpired:
                output, rc = "(command timed out after 120s)", 1

            messages.append({"role": "user", "content": format_observation(output, rc)})

        # Extract patch: always prefer clean git diff from container
        patch = ""
        if not dry_run:
            try:
                # Get staged diff directly (cleanest source)
                patch, _ = docker_exec(container, "cd /app && git diff --cached", timeout=30)
                if not patch.strip():
                    patch, _ = docker_exec(container, "cd /app && git diff", timeout=30)
                if not patch.strip():
                    patch, _ = docker_exec(container, "cd /app && git diff HEAD", timeout=30)
                # git diff must end with newline — docker_exec strips it
                if patch.strip():
                    patch = patch.strip() + "\n"
            except Exception:
                pass
        elif SUBMIT_MARKER in last_output:
            parts = last_output.split(SUBMIT_MARKER, 1)
            if len(parts) > 1:
                patch = parts[1].strip()

        wall_time = time.time() - wall_start
        assistant_turns = sum(1 for m in messages if m["role"] == "assistant")

        # Ensure last message is assistant
        if messages[-1]["role"] != "assistant":
            messages = messages[:-1]

        return {
            "instance_id": instance_id,
            "repo": task.get("repo", ""),
            "language": language,
            "repo_language": language,
            "base_commit": task.get("base_commit", ""),
            "messages": messages,
            "patch": patch,
            "turns": assistant_turns,
            "wall_time": wall_time,
            "fail_to_pass": task.get("fail_to_pass", []),
            "pass_to_pass": task.get("pass_to_pass", []),
            "test_command": task.get("test_command", ""),
            "dockerhub_tag": image,
        }

    finally:
        if container:
            stop_container(container)


# ---------------------------------------------------------------------------
# Patch Verification
# ---------------------------------------------------------------------------

def verify_patch(result: dict) -> float:
    """
    Verify agent's patch by running tests in a fresh container.
    Returns score (1.0 if all fail_to_pass tests pass, else 0.0).
    """
    patch = result.get("patch", "")
    if not patch or not patch.strip():
        return 0.0

    image = result["dockerhub_tag"]
    task_fail_to_pass = set(result.get("fail_to_pass", []))
    test_cmd = result.get("test_command", "")

    if not task_fail_to_pass or not test_cmd:
        # Can't verify without test info — trust the submission
        return 0.5

    container = start_container(image, task=result)
    if not container:
        return 0.0

    try:
        # Apply agent's fix patch via stdin (avoids shell escaping issues)
        r = subprocess.run(
            ["docker", "exec", "-i", container, "bash", "-c",
             "cd /app && git apply -v 2>&1"],
            input=patch, capture_output=True, text=True, timeout=60,
        )
        apply_out = (r.stdout + "\n" + r.stderr).strip()
        if r.returncode != 0:
            print(f"  [VERIFY] Patch apply failed: {apply_out[:200]}")
            return 0.0

        # Run tests
        test_out, test_rc = docker_exec(container, f"cd /app && {test_cmd}", timeout=300)

        # Simple check: if test command exits 0, likely all pass
        if test_rc == 0:
            return 1.0
        return 0.0

    except Exception as e:
        print(f"  [VERIFY] Error: {e}")
        return 0.0
    finally:
        stop_container(container)


# ---------------------------------------------------------------------------
# Quality Filtering
# ---------------------------------------------------------------------------

def passes_quality_filter(result: dict) -> tuple[bool, str]:
    """Check if trajectory meets quality standards. Returns (pass, reason)."""
    messages = result.get("messages", [])
    assistant_msgs = [m for m in messages if m["role"] == "assistant"]

    if len(assistant_msgs) < 3:
        return False, f"too few turns ({len(assistant_msgs)})"
    if len(assistant_msgs) > 40:
        return False, f"too many turns ({len(assistant_msgs)})"

    total_chars = sum(len(m["content"]) for m in messages)
    if total_chars > 120000:
        return False, f"too long ({total_chars} chars)"

    for i, msg in enumerate(assistant_msgs):
        if "THOUGHT" not in msg["content"].upper()[:100]:
            return False, f"assistant msg {i} missing THOUGHT prefix"
        if not ACTION_RE.search(msg["content"]):
            return False, f"assistant msg {i} missing bash block"

    for msg in assistant_msgs:
        if "<think>" in msg["content"]:
            return False, "contains think tags"

    return True, "ok"


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

PREMATURE_REJECT = "ERROR: You have not made any changes yet"


def export_trajectory(result: dict, score: float) -> dict:
    """Convert agent result to training JSONL entry.

    Strips premature-submit rejection messages — these are an artifact
    of our distillation guard, not present in the real eval environment.
    """
    clean_msgs = []
    skip_next = False
    for m in result["messages"]:
        if skip_next:
            skip_next = False
            continue
        if m["role"] == "user" and PREMATURE_REJECT in m["content"]:
            # Remove this rejection AND the preceding assistant submit attempt
            if clean_msgs and clean_msgs[-1]["role"] == "assistant":
                clean_msgs.pop()
            skip_next = False
            continue
        clean_msgs.append(m)

    return {
        "messages": clean_msgs,
        "env": "SWE-INFINITE",
        "score": score,
        "instance_id": result["instance_id"],
        "repo": result["repo"],
        "language": result["language"],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_completed(output_path: str) -> set[str]:
    """Load already-completed instance_ids from output file."""
    completed = set()
    if os.path.exists(output_path):
        with open(output_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    completed.add(entry.get("instance_id", ""))
                except json.JSONDecodeError:
                    pass
    return completed


def process_task(
    task_id: int,
    model: str,
    api_base: str,
    api_key: str,
    output_path: str,
    verify: bool = True,
    dry_run: bool = False,
) -> Optional[dict]:
    """Process a single task end-to-end. Returns stats dict or None."""
    task = load_task(task_id)
    if task is None:
        return None

    instance_id = task.get("instance_id", f"task_{task_id}")
    print(f"\n[Task {task_id}] {instance_id}")

    # Run agent
    result = run_agent(task, model, api_base, api_key, dry_run=dry_run)
    maybe_prune_images()  # prevent disk fill
    if result is None:
        print(f"  [SKIP] Infrastructure failure")
        return {"task_id": task_id, "instance_id": instance_id, "status": "infra_fail"}

    if not result.get("patch"):
        print(f"  [SKIP] No patch generated ({result['turns']} turns, {result['wall_time']:.0f}s)")
        return {"task_id": task_id, "instance_id": instance_id, "status": "no_patch",
                "turns": result["turns"]}

    # Verify
    score = 0.0
    if verify:
        print(f"  Verifying patch...")
        score = verify_patch(result)
        print(f"  Score: {score}")
    else:
        score = 0.5  # unverified

    # Quality filter
    qf_pass, qf_reason = passes_quality_filter(result)
    if score >= 1.0 and qf_pass:
        entry = export_trajectory(result, score)
        with open(output_path, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"  [OK] Exported ({result['turns']} turns, {result['wall_time']:.0f}s)")
        return {"task_id": task_id, "instance_id": instance_id, "status": "success",
                "turns": result["turns"], "score": score}
    elif score >= 1.0:
        print(f"  [SKIP] Failed quality filter: {qf_reason}")
        return {"task_id": task_id, "instance_id": instance_id, "status": "quality_fail",
                "turns": result["turns"], "score": score}
    else:
        print(f"  [SKIP] Score {score} < 1.0 ({result['turns']} turns)")
        return {"task_id": task_id, "instance_id": instance_id, "status": "wrong_answer",
                "turns": result["turns"], "score": score}


def _load_dotenv(path: str = ".env"):
    """Load .env file into os.environ (simple parser, no external deps)."""
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
            if key and key not in os.environ:  # don't override explicit env
                os.environ[key] = val


def main():
    _load_dotenv()
    parser = argparse.ArgumentParser(description="SWE-Infinite trajectory distillation")
    parser.add_argument("--model", default="gpt-5.4", help="LLM model name (default: gpt-5.4)")
    parser.add_argument("--api-base", default=os.getenv("OPENAI_BASE_URL", ""),
                        help="OpenAI-compatible API base URL (default: $OPENAI_BASE_URL)")
    parser.add_argument("--api-key", default=os.getenv("OPENAI_API_KEY", ""),
                        help="API key (default: $OPENAI_API_KEY)")
    parser.add_argument("--task-range", default="",
                        help="Task ID range (e.g. 1-345 or 1,5,10)")
    parser.add_argument("--task-file", default="",
                        help="JSONL file with task dicts (alternative to --task-range)")
    parser.add_argument("--output", default="data/swe_infinite_trajectories.jsonl",
                        help="Output JSONL path")
    parser.add_argument("--workers", type=int, default=1,
                        help="Concurrent workers (default: 1)")
    parser.add_argument("--no-verify", action="store_true",
                        help="Skip patch verification (faster but no score)")
    parser.add_argument("--resume", action="store_true",
                        help="Skip already-completed tasks")
    parser.add_argument("--dry-run", action="store_true",
                        help="Test without Docker (simulates command execution)")
    parser.add_argument("--local-only", action="store_true",
                        help="Skip DockerHub pulls, use local build only (saves rate limit)")
    args = parser.parse_args()

    global _local_only
    _local_only = args.local_only

    if not args.api_key:
        print("ERROR: --api-key or $OPENAI_API_KEY required")
        sys.exit(1)

    # Load tasks from file or parse range
    direct_tasks = []  # list of task dicts from --task-file
    task_ids = []      # list of int IDs from --task-range

    if args.task_file:
        with open(args.task_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    direct_tasks.append(json.loads(line))
        print(f"Loaded {len(direct_tasks)} tasks from {args.task_file}")
    elif args.task_range:
        if "," in args.task_range:
            task_ids = [int(x.strip()) for x in args.task_range.split(",")]
        elif "-" in args.task_range:
            lo, hi = args.task_range.split("-", 1)
            task_ids = list(range(int(lo), int(hi) + 1))
        else:
            task_ids = [int(args.task_range)]
    else:
        print("ERROR: need --task-range or --task-file")
        sys.exit(1)

    # Resume: skip completed
    completed = load_completed(args.output) if args.resume else set()
    if completed:
        print(f"Resuming: {len(completed)} tasks already completed")

    # Build pending list — dedup by instance_id at source
    seen_ids = set(completed)
    if direct_tasks:
        pending_tasks = []
        for t in direct_tasks:
            iid = t.get("instance_id", "")
            if iid not in seen_ids:
                seen_ids.add(iid)
                pending_tasks.append(t)
        print(f"Tasks: {len(pending_tasks)} pending (of {len(direct_tasks)} total)")
    else:
        pending_tasks = []
        for tid in task_ids:
            task = load_task(tid)
            if task is None:
                continue
            if task.get("instance_id") in completed:
                continue
            pending_tasks.append(task)
        print(f"Tasks: {len(pending_tasks)} pending (of {len(task_ids)} total)")

    print(f"Model: {args.model}")
    print(f"Output: {args.output}")
    print(f"Verify: {not args.no_verify}")

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    stats = {"success": 0, "wrong_answer": 0, "no_patch": 0, "infra_fail": 0, "quality_fail": 0}
    retry_queue = []  # tasks that failed due to API, will retry once

    def _process_one(task, label):
        instance_id = task.get("instance_id", "?")
        print(f"\n[{label}] {instance_id} ({task.get('repo_language', '?')})")

        result = run_agent(task, args.model, args.api_base, args.api_key, dry_run=args.dry_run)
        maybe_prune_images()

        if result is None:
            print(f"  [INFRA_FAIL]")
            stats["infra_fail"] += 1
            return "infra_fail"

        if not result.get("patch"):
            if result["turns"] == 0:
                # API failure — eligible for retry
                print(f"  [API_FAIL] 0 turns — will retry")
                return "api_fail"
            print(f"  [NO_PATCH] {result['turns']} turns, {result['wall_time']:.0f}s")
            stats["no_patch"] += 1
            return "no_patch"

        score = 0.0
        if not args.no_verify:
            print(f"  Verifying...")
            score = verify_patch(result)
            print(f"  Score: {score}")
        else:
            score = 0.5

        qf_pass, qf_reason = passes_quality_filter(result)
        if score >= 1.0 and qf_pass:
            entry = export_trajectory(result, score)
            with open(args.output, "a") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            seen_ids.add(instance_id)  # prevent re-processing
            print(f"  [OK] Exported ({result['turns']} turns, {result['wall_time']:.0f}s)")
            stats["success"] += 1
            return "success"
        elif score >= 1.0:
            print(f"  [QUALITY_FAIL] {qf_reason}")
            stats["quality_fail"] += 1
            return "quality_fail"
        else:
            print(f"  [WRONG] Score {score} ({result['turns']} turns)")
            stats["wrong_answer"] += 1
            return "wrong_answer"

    # Main pass
    for i, task in enumerate(pending_tasks):
        status = _process_one(task, f"{i+1}/{len(pending_tasks)}")
        if status == "api_fail":
            retry_queue.append(task)

    # Retry pass for API failures
    if retry_queue:
        print(f"\n{'='*50}")
        print(f"RETRY PASS: {len(retry_queue)} API-failed tasks")
        print(f"{'='*50}")
        time.sleep(30)  # wait before retry
        still_failed = 0
        for i, task in enumerate(retry_queue):
            status = _process_one(task, f"R{i+1}/{len(retry_queue)}")
            if status == "api_fail":
                stats["no_patch"] += 1
                still_failed += 1
        print(f"Retry: {len(retry_queue) - still_failed} recovered, {still_failed} still failed")

    # Summary
    total = sum(stats.values())
    print(f"\n{'='*60}")
    print(f"DISTILLATION COMPLETE")
    print(f"  Total processed:  {total}")
    print(f"  Success:          {stats['success']}")
    print(f"  Wrong answer:     {stats['wrong_answer']}")
    print(f"  No patch:         {stats['no_patch']}")
    print(f"  Quality fail:     {stats['quality_fail']}")
    print(f"  Infra fail:       {stats['infra_fail']}")
    if total > 0:
        print(f"  Success rate:     {stats['success']/total*100:.1f}%")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
