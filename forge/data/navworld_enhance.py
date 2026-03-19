"""NAVWORLD data quality enhancement using Claude API.

Scores existing entries, rewrites low-quality ones with two-pass pipeline
(Sonnet generates -> Haiku critiques -> Sonnet fixes), and replaces in canonical.

Usage via CLI: forge data navworld-enhance [--score-only] [--rewrite-n N]
"""

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import anthropic

from forge.config import PROJECT_ROOT

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-20250514"

# Pricing per million tokens (USD)
PRICING = {
    HAIKU:  {"input": 0.80, "output": 4.00},
    SONNET: {"input": 3.00, "output": 15.00},
}

CANONICAL_PATH = PROJECT_ROOT / "data" / "canonical" / "navworld.jsonl"

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

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

REWRITE_PROMPT = """你是旅行规划评测系统的"完美回答生成器"。你的任务是根据工具返回的真实数据，生成一份能拿高分的旅行规划。

## 评分标准（满分50分，5维度×10分）

### 1. factual_grounding（事实引用，10分）— 最重要！
- 每个航班号、车次号必须从工具结果中**逐字复制**
- 每个价格必须有工具来源
- 每个POI名称必须出自poi_search/around_search结果
- 天气数据必须引用weather工具返回的具体天气和温度
- 距离和时间必须引用direction工具返回的数值
- **编造任何一个数据 = 扣分**

### 2. analysis_depth（分析深度，10分）
- 不要罗列数据！要分析trade-off
- 错误示范："G7756 20:00出发，票价435元"
- 正确示范："G7756次20:00出发，票价435元（二等座），虽然出发较晚但仅需1小时40分钟，适合不赶时间且希望节省预算的旅客。相比Z1006（89元但需11小时），G7756在时间和价格之间取得了最佳平衡。"

### 3. practicality（实用性，10分）
- 必须有具体时间段安排（上午/下午/晚上具体几点）
- 每段行程标注交通方式和耗时
- 跨城市行程必须有具体的出发/到达时间

### 4. logic（逻辑性，10分）
- 景点顺序要地理合理，不要来回跑
- 引用direction工具的距离来证明路线合理性
- 如果天气预报有雨，要调整室外行程

### 5. user_experience（用户体验，10分）
- 明确回应用户的预算约束（计算总费用 vs 预算）
- 回应用户的偏好（经济/舒适/速度）
- 回应用户的兴趣（美食/摄影/亲子等）

## 用户请求
{user_query}

## 工具返回数据（这是唯一可用的事实来源！）
{tool_results}

## 输出格式
直接输出中文旅行规划方案（800-2500字）。开头用标题概括。结尾必须有总预算明细。"""

CRITIQUE_PROMPT = """你是旅行规划质量审核员。检查以下规划方案，找出所有问题。

## 检查清单
1. **数据编造**: 方案中提到的航班号、车次号、价格、POI名是否都能在工具数据中找到？列出所有编造的数据。
2. **遗漏引用**: 工具返回了哪些重要数据没被方案引用？（天气、距离、价格等）
3. **分析不足**: 哪些地方只是罗列数据而没有分析推荐理由？
4. **逻辑问题**: 时间安排是否合理？路线是否地理上合理？
5. **用户约束**: 预算是否被回应？偏好是否被考虑？

## 工具数据
{tool_results}

## 用户请求
{user_query}

## 待审方案
{plan}

列出所有问题，每个问题一行，格式："[维度] 问题描述"。如果方案质量很高（无编造、分析充分），输出"PASS"。"""

FIX_PROMPT = """根据审核意见修复旅行规划方案。修复所有指出的问题，特别是：
- 删除所有编造的数据，只保留工具结果中存在的数据
- 补充遗漏的重要数据引用
- 将数据罗列改为分析推荐
- 修复逻辑问题

## 审核意见
{critique}

## 原方案
{plan}

## 工具数据（唯一事实来源）
{tool_results}

## 用户请求
{user_query}

输出修复后的完整方案（800-2500字）。"""


# ---------------------------------------------------------------------------
# Cost tracking
# ---------------------------------------------------------------------------

@dataclass
class CostTracker:
    """Tracks API token usage and estimated cost."""
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
    _by_model: dict = field(default_factory=dict)

    def add(self, model: str, input_tok: int, output_tok: int):
        self.input_tokens += input_tok
        self.output_tokens += output_tok
        self.calls += 1
        if model not in self._by_model:
            self._by_model[model] = {"input": 0, "output": 0, "calls": 0}
        self._by_model[model]["input"] += input_tok
        self._by_model[model]["output"] += output_tok
        self._by_model[model]["calls"] += 1

    @property
    def estimated_usd(self) -> float:
        total = 0.0
        for model, usage in self._by_model.items():
            p = PRICING.get(model, {"input": 3.0, "output": 15.0})
            total += usage["input"] * p["input"] / 1e6
            total += usage["output"] * p["output"] / 1e6
        return total

    def summary(self) -> str:
        lines = [f"API calls: {self.calls}"]
        lines.append(f"Total tokens: {self.input_tokens:,} in / {self.output_tokens:,} out")
        for model, usage in self._by_model.items():
            short = model.split("-")[1] if "-" in model else model
            lines.append(f"  {short}: {usage['calls']} calls, {usage['input']:,} in / {usage['output']:,} out")
        lines.append(f"Estimated cost: ${self.estimated_usd:.3f}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Client helper
# ---------------------------------------------------------------------------

def get_claude_client() -> anthropic.Anthropic:
    """Create Anthropic client from env vars (ANTHROPIC_BASE_URL, ANTHROPIC_API_KEY)."""
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env", override=True)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    base_url = os.getenv("ANTHROPIC_BASE_URL")

    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set in environment or .env")

    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return anthropic.Anthropic(**kwargs)


# ---------------------------------------------------------------------------
# Entry extraction helpers
# ---------------------------------------------------------------------------

def _extract_plan_summary(entry: dict) -> str:
    """Extract user query + tool results summary + final plan for scoring."""
    msgs = entry.get("messages", [])
    parts = []
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


def _extract_parts(entry: dict) -> tuple:
    """Extract (user_query, tool_results_text) for rewriting."""
    msgs = entry.get("messages", [])
    user_query = ""
    parts = []

    for m in msgs:
        role = m["role"]
        content = m.get("content", "")
        if role == "user" and not user_query:
            user_query = content
        elif role == "assistant" and "<tool_call>" in content:
            parts.append(f"[调用工具]:\n{content}")
        elif role == "tool":
            parts.append(f"[工具返回]:\n{content}")

    return user_query, "\n\n".join(parts)


def _parse_json_response(text: str) -> Optional[dict]:
    """Extract JSON object from model response text."""
    if "{" not in text:
        return None
    try:
        json_str = text[text.index("{"):text.rindex("}") + 1]
        return json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

async def score_entries(
    entries: list[dict],
    client: anthropic.Anthropic,
    n: int = 200,
    concurrency: int = 10,
    cost: Optional[CostTracker] = None,
) -> list[dict]:
    """Score entries on 5 eval dimensions using Haiku.

    Args:
        entries: list of NAVWORLD conversation entries
        client: Anthropic client
        n: number of entries to score (samples if n < len(entries))
        concurrency: max parallel API calls
        cost: optional CostTracker to accumulate usage

    Returns:
        list of score dicts with keys: entry_idx, analysis_depth, factual_grounding,
        practicality, logic, user_experience, total, weakest, note
    """
    import random

    if cost is None:
        cost = CostTracker()

    # Sample if needed
    indices = list(range(len(entries)))
    if n < len(entries):
        random.seed(42)
        indices = sorted(random.sample(indices, n))

    sem = asyncio.Semaphore(concurrency)
    scored = 0
    total_to_score = len(indices)

    async def _score_one(idx: int) -> dict:
        nonlocal scored
        async with sem:
            summary = _extract_plan_summary(entries[idx])
            try:
                resp = await asyncio.to_thread(
                    client.messages.create,
                    model=HAIKU,
                    max_tokens=200,
                    messages=[
                        {"role": "user", "content": f"{SCORING_PROMPT}\n\n---\n\n{summary}"}
                    ],
                )
                cost.add(HAIKU, resp.usage.input_tokens, resp.usage.output_tokens)
                scores = _parse_json_response(resp.content[0].text.strip())
                scored += 1

                if scores:
                    scores["entry_idx"] = idx
                    print(f"  [{scored}/{total_to_score}] idx={idx} total={scores.get('total', '?')} weakest={scores.get('weakest', '?')}")
                    return scores
                else:
                    print(f"  [{scored}/{total_to_score}] idx={idx} ERROR: no JSON in response")
                    return {"entry_idx": idx, "error": "no_json"}
            except Exception as e:
                scored += 1
                print(f"  [{scored}/{total_to_score}] idx={idx} ERROR: {e}")
                return {"entry_idx": idx, "error": str(e)}

    tasks = [_score_one(idx) for idx in indices]
    results = await asyncio.gather(*tasks)
    return results


async def rewrite_plan(
    entry: dict,
    client: anthropic.Anthropic,
    cost: Optional[CostTracker] = None,
) -> Optional[dict]:
    """Two-pass rewrite: Sonnet generates -> Haiku critiques -> Sonnet fixes.

    Args:
        entry: single NAVWORLD conversation entry
        client: Anthropic client
        cost: optional CostTracker

    Returns:
        new entry with rewritten plan, or None on failure
    """
    if cost is None:
        cost = CostTracker()

    user_query, tool_results = _extract_parts(entry)
    tool_results_truncated = tool_results[:15000]

    try:
        # Pass 1: Sonnet rewrites
        resp1 = await asyncio.to_thread(
            client.messages.create,
            model=SONNET,
            max_tokens=3000,
            messages=[{"role": "user", "content": REWRITE_PROMPT.format(
                user_query=user_query,
                tool_results=tool_results_truncated,
            )}],
        )
        plan_v1 = resp1.content[0].text.strip()
        cost.add(SONNET, resp1.usage.input_tokens, resp1.usage.output_tokens)

        # Pass 2: Haiku critiques
        resp2 = await asyncio.to_thread(
            client.messages.create,
            model=HAIKU,
            max_tokens=1000,
            messages=[{"role": "user", "content": CRITIQUE_PROMPT.format(
                tool_results=tool_results_truncated[:8000],
                user_query=user_query,
                plan=plan_v1,
            )}],
        )
        critique = resp2.content[0].text.strip()
        cost.add(HAIKU, resp2.usage.input_tokens, resp2.usage.output_tokens)

        # If critique passes, use v1 directly
        if "PASS" in critique and len(critique) < 50:
            final_plan = plan_v1
        else:
            # Pass 3: Sonnet fixes based on critique
            resp3 = await asyncio.to_thread(
                client.messages.create,
                model=SONNET,
                max_tokens=3000,
                messages=[{"role": "user", "content": FIX_PROMPT.format(
                    critique=critique,
                    plan=plan_v1,
                    tool_results=tool_results_truncated[:10000],
                    user_query=user_query,
                )}],
            )
            final_plan = resp3.content[0].text.strip()
            cost.add(SONNET, resp3.usage.input_tokens, resp3.usage.output_tokens)

        if len(final_plan) < 200:
            return None

        # Replace the final assistant plan in the entry
        new_entry = json.loads(json.dumps(entry))
        for i in range(len(new_entry["messages"]) - 1, -1, -1):
            m = new_entry["messages"][i]
            if m["role"] == "assistant" and "<tool_call>" not in m.get("content", ""):
                new_entry["messages"][i]["content"] = final_plan
                break

        return new_entry

    except Exception as e:
        print(f"  Rewrite error: {e}")
        return None


async def verify_improvement(
    old_entry: dict,
    new_entry: dict,
    client: anthropic.Anthropic,
    cost: Optional[CostTracker] = None,
) -> dict:
    """Re-score old and new entries, confirm improvement.

    Returns:
        dict with old_score, new_score, improved (bool), delta
    """
    if cost is None:
        cost = CostTracker()

    old_results = await score_entries([old_entry], client, n=1, concurrency=1, cost=cost)
    new_results = await score_entries([new_entry], client, n=1, concurrency=1, cost=cost)

    old_score = old_results[0].get("total", 0) if old_results else 0
    new_score = new_results[0].get("total", 0) if new_results else 0

    return {
        "old_score": old_score,
        "new_score": new_score,
        "delta": new_score - old_score,
        "improved": new_score > old_score,
        "old_detail": old_results[0] if old_results else {},
        "new_detail": new_results[0] if new_results else {},
    }


async def enhance_batch(
    canonical_path: Path,
    client: anthropic.Anthropic,
    target_score: int = 15,
    max_rewrites: int = 50,
    score_sample: int = 200,
    concurrency: int = 5,
    dry_run: bool = False,
    score_only: bool = False,
) -> dict:
    """Full enhancement pipeline: score -> filter bottom -> rewrite -> verify -> replace.

    Args:
        canonical_path: path to navworld.jsonl
        client: Anthropic client
        target_score: minimum acceptable total score (out of 50)
        max_rewrites: max entries to rewrite per run
        score_sample: how many entries to score for triage
        concurrency: parallel API calls for rewriting
        dry_run: if True, don't modify canonical file
        score_only: if True, only score and report

    Returns:
        dict with stats: scored, below_target, rewritten, improved, cost, etc.
    """
    cost = CostTracker()

    # Load canonical entries
    with open(canonical_path) as f:
        entries = [json.loads(line) for line in f]
    print(f"Loaded {len(entries)} entries from {canonical_path}")

    # Phase 1: Score
    print(f"\n--- Phase 1: Scoring {min(score_sample, len(entries))} entries ---")
    scores = await score_entries(entries, client, n=score_sample, concurrency=10, cost=cost)
    valid_scores = [s for s in scores if "total" in s]
    valid_scores.sort(key=lambda x: x["total"])

    if not valid_scores:
        return {"error": "No valid scores obtained", "cost": cost.summary()}

    avg_total = sum(s["total"] for s in valid_scores) / len(valid_scores)
    dims = ["analysis_depth", "factual_grounding", "practicality", "logic", "user_experience"]

    print(f"\nScored {len(valid_scores)} entries, avg total: {avg_total:.1f}/50")
    for d in dims:
        avg = sum(s.get(d, 0) for s in valid_scores) / len(valid_scores)
        print(f"  {d}: {avg:.1f}/10")

    below_target = [s for s in valid_scores if s["total"] < target_score]
    print(f"Below target ({target_score}): {len(below_target)}/{len(valid_scores)}")

    result = {
        "total_entries": len(entries),
        "scored": len(valid_scores),
        "avg_score": round(avg_total, 1),
        "below_target": len(below_target),
        "target_score": target_score,
        "dimension_avgs": {d: round(sum(s.get(d, 0) for s in valid_scores) / len(valid_scores), 1) for d in dims},
    }

    if score_only:
        result["cost"] = cost.summary()
        return result

    if not below_target:
        print("No entries below target score. Nothing to rewrite.")
        result["rewritten"] = 0
        result["cost"] = cost.summary()
        return result

    # Phase 2: Rewrite bottom entries
    to_rewrite = below_target[:max_rewrites]
    print(f"\n--- Phase 2: Rewriting {len(to_rewrite)} entries (concurrency={concurrency}) ---")

    sem = asyncio.Semaphore(concurrency)
    rewritten_count = 0
    improved_count = 0
    replacements = {}  # entry_idx -> new_entry

    async def _rewrite_one(score_record: dict) -> Optional[dict]:
        nonlocal rewritten_count
        async with sem:
            idx = score_record["entry_idx"]
            old_entry = entries[idx]

            new_entry = await rewrite_plan(old_entry, client, cost=cost)
            rewritten_count += 1

            if new_entry is None:
                print(f"  [{rewritten_count}/{len(to_rewrite)}] idx={idx} FAILED")
                return None

            print(f"  [{rewritten_count}/{len(to_rewrite)}] idx={idx} rewritten (old_score={score_record['total']})")
            return {"idx": idx, "new_entry": new_entry, "old_score": score_record["total"]}

    tasks = [_rewrite_one(s) for s in to_rewrite]
    rewrite_results = await asyncio.gather(*tasks)
    successful = [r for r in rewrite_results if r is not None]

    # Phase 3: Verify improvements (sample up to 10 for cost efficiency)
    verify_sample = successful[:10]
    if verify_sample:
        print(f"\n--- Phase 3: Verifying {len(verify_sample)} rewrites ---")
        for r in verify_sample:
            v = await verify_improvement(entries[r["idx"]], r["new_entry"], client, cost=cost)
            r["verification"] = v
            if v["improved"]:
                improved_count += 1
                print(f"  idx={r['idx']}: {v['old_score']} -> {v['new_score']} (+{v['delta']})")
            else:
                print(f"  idx={r['idx']}: {v['old_score']} -> {v['new_score']} (no improvement, keeping anyway)")

    # Phase 4: Replace in canonical (unless dry_run)
    # Accept all successful rewrites (the two-pass pipeline is the quality gate)
    for r in successful:
        replacements[r["idx"]] = r["new_entry"]

    result["rewritten"] = len(successful)
    result["failed"] = len(to_rewrite) - len(successful)
    result["verified_sample"] = len(verify_sample)
    result["verified_improved"] = improved_count

    if dry_run:
        print(f"\n[DRY RUN] Would replace {len(replacements)} entries in canonical")
        result["dry_run"] = True
        result["would_replace"] = len(replacements)
    elif replacements:
        print(f"\n--- Phase 4: Replacing {len(replacements)} entries in canonical ---")
        for idx, new_entry in replacements.items():
            entries[idx] = new_entry

        with open(canonical_path, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"Written {len(entries)} entries to {canonical_path}")
        result["replaced"] = len(replacements)

    result["cost"] = cost.summary()
    return result
