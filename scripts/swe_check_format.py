#!/usr/bin/env python3
"""Check format consistency between GPT-5.4 and Claude trajectories."""
import json, glob, sys

def check_trajectory(entry, source):
    """Check a single trajectory for format compliance."""
    msgs = entry.get("messages", [])
    issues = []

    # Check messages exist
    if not msgs:
        issues.append("NO_MESSAGES")
        return issues

    # Check last message is assistant
    if msgs[-1]["role"] != "assistant":
        issues.append("LAST_NOT_ASSISTANT")

    for m in msgs:
        if m["role"] == "assistant":
            content = m.get("content", "")
            # Check for <think> tags (FORBIDDEN)
            if "<think>" in content:
                issues.append("HAS_THINK_TAGS")
            # Check for THOUGHT format
            if "THOUGHT:" not in content and "THOUGHT" not in content[:50]:
                issues.append("NO_THOUGHT_PREFIX")
            # Check for bash block
            if "```bash" not in content and "```\nbash" not in content:
                issues.append("NO_BASH_BLOCK")
            # Check for tool_calls (FORBIDDEN)
            if "tool_calls" in content or "function_call" in content:
                issues.append("HAS_TOOL_CALLS")
            break  # Only check first assistant message

    return issues

# Check GPT-5.4 trajectories
print("=== GPT-5.4 Trajectories ===")
gpt_files = glob.glob("/root/real_distill_v*.jsonl")
gpt_total = 0
gpt_issues = {}
for f in gpt_files:
    for line in open(f):
        try:
            entry = json.loads(line)
            issues = check_trajectory(entry, "gpt")
            gpt_total += 1
            for i in issues:
                gpt_issues[i] = gpt_issues.get(i, 0) + 1
        except: pass
print(f"Total: {gpt_total}")
print(f"Issues: {gpt_issues if gpt_issues else 'NONE'}")

# Check Claude trajectories
print("\n=== Claude Trajectories ===")
claude_files = glob.glob("/root/real_distill_swe_batch_all_uncovered_w*.jsonl")
claude_total = 0
claude_issues = {}
for f in claude_files:
    for line in open(f):
        try:
            entry = json.loads(line)
            issues = check_trajectory(entry, "claude")
            claude_total += 1
            for i in issues:
                claude_issues[i] = claude_issues.get(i, 0) + 1
        except: pass
print(f"Total: {claude_total}")
print(f"Issues: {claude_issues if claude_issues else 'NONE'}")

# Compare a sample
print("\n=== Sample Comparison ===")
for label, files in [("GPT", gpt_files[:1]), ("Claude", claude_files[:1])]:
    for f in files:
        try:
            entry = json.loads(open(f).readline())
            msgs = entry["messages"]
            for m in msgs:
                if m["role"] == "assistant":
                    print(f"\n{label} first assistant (first 200 chars):")
                    print(m["content"][:200])
                    print(f"  ...total len: {len(m['content'])}")
                    break
        except: pass
