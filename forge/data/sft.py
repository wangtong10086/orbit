"""SFT data extraction, quality filtering, and analysis."""

import json
import os
import re
import time
from typing import Optional


# ===== Environment-specific cleaners =====
# Each returns cleaned record or None if unusable.

def _clean_game(record: dict) -> Optional[dict]:
    """GAME: multi-turn game playing. Validate complete conversations."""
    msgs = record["messages"]
    # Must have system prompt
    if not msgs or msgs[0]["role"] != "system":
        return None
    # Must have at least 1 user + 1 assistant turn after system
    roles_after_sys = [m["role"] for m in msgs[1:]]
    if "assistant" not in roles_after_sys or "user" not in roles_after_sys:
        return None
    # Last message should be from assistant (completed game)
    if msgs[-1]["role"] != "assistant":
        return None
    # Filter empty assistant responses
    record["messages"] = [m for m in msgs if m["content"].strip()]
    if len(record["messages"]) < 3:
        return None
    return record


def _clean_lgc(record: dict) -> Optional[dict]:
    """LGC-v2: logic/math puzzles. Validate complete reasoning."""
    msgs = record["messages"]
    if len(msgs) != 2:
        return None
    user_msg, asst_msg = msgs[0], msgs[1]
    if user_msg["role"] != "user" or asst_msg["role"] != "assistant":
        return None
    content = asst_msg["content"]
    # Verify think block is closed (not truncated)
    if "<think>" in content and "</think>" not in content:
        return None
    # If task asks for python code, verify it's present
    if "```python" in user_msg["content"] and "```python" not in content:
        return None
    # Must have substantive answer (not just empty think block)
    if "<think>" in content:
        after_think = content.split("</think>")[-1].strip()
        if len(after_think) < 1:
            return None
    # Minimum content length - filter out empty/trivial responses
    if len(content.strip()) < 10:
        return None
    return record


def _clean_print(record: dict) -> Optional[dict]:
    """PRINT: predict program output. Must have complete reasoning."""
    msgs = record["messages"]
    if len(msgs) != 2:
        return None
    user_msg, asst_msg = msgs[0], msgs[1]
    if user_msg["role"] != "user" or asst_msg["role"] != "assistant":
        return None
    content = asst_msg["content"]
    # Verify think block is closed
    if "<think>" in content and "</think>" not in content:
        return None
    # Must have some content after think block (the actual answer)
    after_think = content.split("</think>")[-1].strip() if "</think>" in content else content.strip()
    if len(after_think) < 1:
        return None
    return record


def _clean_swe_synth(record: dict) -> Optional[dict]:
    """SWE-SYNTH: multi-turn code fix. Validate structure."""
    msgs = record["messages"]
    if len(msgs) < 4:
        return None
    # Should have system prompt
    if msgs[0]["role"] != "system":
        return None
    # Must have at least one assistant response with actual code/thought
    has_substance = any(
        m["role"] == "assistant" and len(m["content"]) > 20
        for m in msgs
    )
    if not has_substance:
        return None
    # Strip trailing non-assistant messages (DynamoDB samples often end with user)
    while msgs and msgs[-1]["role"] != "assistant":
        msgs.pop()
    record["messages"] = msgs
    if len(msgs) < 4:
        return None
    return record


NAVWORLD_REASONING_WORDS = re.compile(
    r"因为|由于|所以|因此|建议|推荐|考虑到|综合|权衡|对比|相比|优先|适合"
)
NAVWORLD_TOOLS = {"poi_search", "around_search", "weather", "direction", "search_flights", "search_train_tickets"}


def _clean_navworld(record: dict) -> Optional[dict]:
    """NAVWORLD: travel planning with tool calls. Validate against scorer requirements."""
    msgs = record["messages"]
    if len(msgs) < 7:
        return None
    content = " ".join(m.get("content", "") for m in msgs)

    # Must have tool calls
    if "调用工具" not in content and "tool_call" not in content.lower():
        return None

    # Must have poi_search (core tool, required by scorer)
    if "poi_search" not in content:
        return None

    # Count distinct tools used (scorer penalizes missing tools)
    tools_used = sum(1 for t in NAVWORLD_TOOLS if t in content)
    if tools_used < 3:
        return None

    # Final assistant message must be substantial (scorer: format_valid needs ≥100 chars)
    assistant_msgs = [m for m in msgs if m["role"] == "assistant"]
    if not assistant_msgs:
        return None
    final = assistant_msgs[-1].get("content", "")
    if len(final) < 200:
        return None

    # Scorer checks reasoning connectors (template detection penalty)
    reasoning_count = len(NAVWORLD_REASONING_WORDS.findall(final))
    if len(final) > 500 and reasoning_count < 3:
        return None

    return record


def _clean_liveweb(record: dict) -> Optional[dict]:
    """LIVEWEB: browser agent. Basic validation."""
    msgs = record["messages"]
    if len(msgs) < 3:
        return None
    if not any(m["role"] == "assistant" for m in msgs):
        return None
    return record


# Registry: env name -> cleaner function
ENV_CLEANERS: dict[str, callable] = {
    "GAME": _clean_game,
    "LGC-v2": _clean_lgc,
    "PRINT": _clean_print,
    "SWE-SYNTH": _clean_swe_synth,
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
    """Deep quality audit of NAVWORLD data aligned with scorer.py requirements.

    Returns summary stats and per-record issues.
    """
    results = {"total": len(records), "pass": 0, "fail": 0, "issues": {}, "tool_coverage": {}}
    issue_counts: dict[str, int] = {}

    for i, r in enumerate(records):
        msgs = r.get("messages", [])
        content = " ".join(m.get("content", "") for m in msgs)
        problems = []

        # 1. Tool diversity
        tools_used = [t for t in NAVWORLD_TOOLS if t in content]
        for t in tools_used:
            results["tool_coverage"][t] = results["tool_coverage"].get(t, 0) + 1
        if len(tools_used) < 4:
            problems.append(f"tools<4 ({len(tools_used)}: {','.join(tools_used)})")

        # 2. Final plan quality
        assistant_msgs = [m for m in msgs if m["role"] == "assistant"]
        final = assistant_msgs[-1].get("content", "") if assistant_msgs else ""
        if len(final) < 500:
            problems.append(f"final_short ({len(final)} chars)")

        # 3. Reasoning connectors (scorer template detection)
        reasoning_count = len(NAVWORLD_REASONING_WORDS.findall(final))
        if reasoning_count < 5:
            problems.append(f"reasoning_low ({reasoning_count})")

        # 4. Format keywords by problem type
        problem_type = r.get("problem_type", "")
        type_keywords = {
            "intercity": r"航班|火车|高铁|飞机|车次",
            "multiday": r"第\d+天|Day\d+",
            "hybrid": r"航班|火车|第\d+天",
            "single_poi": r"景点|游览|路线|门票",
            "food_tour": r"美食|餐厅|小吃|特色",
            "business": r"航班|火车|商务|酒店",
            "family_study": r"亲子|儿童|博物馆|科技馆",
        }
        if problem_type in type_keywords:
            if not re.search(type_keywords[problem_type], final):
                problems.append(f"missing_type_keywords ({problem_type})")

        # 5. POI grounding (must reference tool-returned POIs)
        tool_results = " ".join(
            m.get("content", "") for m in msgs if m["role"] == "user" and "工具调用结果" in m.get("content", "")
        )
        if "poi_search" in content and tool_results:
            # Check if any POI from tool results appears in final plan
            # Simple heuristic: look for Chinese place names (2-8 chars) from tool results
            poi_in_final = any(
                word in final
                for word in re.findall(r'(?:name|名称)["\s:：]+([^",\n]{2,15})', tool_results)
            )
            if not poi_in_final and len(final) > 300:
                problems.append("poi_not_grounded")

        if problems:
            results["fail"] += 1
            for p in problems:
                tag = p.split(" ")[0]
                issue_counts[tag] = issue_counts.get(tag, 0) + 1
        else:
            results["pass"] += 1

    results["issues"] = dict(sorted(issue_counts.items(), key=lambda x: -x[1]))
    results["pass_rate"] = results["pass"] / max(results["total"], 1)
    return results


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


