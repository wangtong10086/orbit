#!/usr/bin/env python3
"""N2v2: Two-pass rewrite with self-critique for NAVWORLD plans.

Pass 1: Claude Sonnet rewrites plan with strict grounding rules
Pass 2: Claude Haiku critiques the rewrite, Sonnet fixes issues
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

import anthropic

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


def extract_parts(entry: dict) -> tuple[str, str]:
    """Extract user query and formatted tool results."""
    msgs = entry["messages"]
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


async def rewrite_with_critique(client, entry_idx: int, entry: dict, semaphore) -> dict | None:
    """Two-pass rewrite: generate → critique → fix."""
    async with semaphore:
        user_query, tool_results = extract_parts(entry)
        tool_results_truncated = tool_results[:15000]

        total_input = 0
        total_output = 0

        try:
            # Pass 1: Sonnet rewrites
            resp1 = await asyncio.to_thread(
                client.messages.create,
                model="claude-sonnet-4-20250514",
                max_tokens=3000,
                messages=[{"role": "user", "content": REWRITE_PROMPT.format(
                    user_query=user_query,
                    tool_results=tool_results_truncated,
                )}],
            )
            plan_v1 = resp1.content[0].text.strip()
            total_input += resp1.usage.input_tokens
            total_output += resp1.usage.output_tokens

            # Pass 2: Haiku critiques
            resp2 = await asyncio.to_thread(
                client.messages.create,
                model="claude-haiku-4-5-20251001",
                max_tokens=1000,
                messages=[{"role": "user", "content": CRITIQUE_PROMPT.format(
                    tool_results=tool_results_truncated[:8000],
                    user_query=user_query,
                    plan=plan_v1,
                )}],
            )
            critique = resp2.content[0].text.strip()
            total_input += resp2.usage.input_tokens
            total_output += resp2.usage.output_tokens

            # If critique says PASS, use v1
            if "PASS" in critique and len(critique) < 50:
                final_plan = plan_v1
                print(f"  [{entry_idx}] PASS on first try ({len(plan_v1)} chars)")
            else:
                # Pass 3: Sonnet fixes based on critique
                resp3 = await asyncio.to_thread(
                    client.messages.create,
                    model="claude-sonnet-4-20250514",
                    max_tokens=3000,
                    messages=[{"role": "user", "content": FIX_PROMPT.format(
                        critique=critique,
                        plan=plan_v1,
                        tool_results=tool_results_truncated[:10000],
                        user_query=user_query,
                    )}],
                )
                final_plan = resp3.content[0].text.strip()
                total_input += resp3.usage.input_tokens
                total_output += resp3.usage.output_tokens
                print(f"  [{entry_idx}] Fixed after critique ({len(final_plan)} chars, critique: {len(critique)} chars)")

            if len(final_plan) < 200:
                print(f"  [{entry_idx}] WARN: too short")
                return None

            # Replace plan in entry
            new_entry = json.loads(json.dumps(entry))
            for i in range(len(new_entry["messages"]) - 1, -1, -1):
                m = new_entry["messages"][i]
                if m["role"] == "assistant" and "<tool_call>" not in m.get("content", ""):
                    new_entry["messages"][i]["content"] = final_plan
                    break

            return {
                "entry_idx": entry_idx,
                "new_entry": new_entry,
                "plan_len": len(final_plan),
                "had_critique": "PASS" not in critique or len(critique) >= 50,
                "input_tokens": total_input,
                "output_tokens": total_output,
            }

        except Exception as e:
            print(f"  [{entry_idx}] ERROR: {e}")
            return None


async def main():
    scores_file = sys.argv[1] if len(sys.argv) > 1 else "data/navworld_scores.jsonl"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    output = sys.argv[3] if len(sys.argv) > 3 else "data/navworld_rewritten_v2.jsonl"

    client = anthropic.Anthropic(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        base_url=os.getenv("ANTHROPIC_BASE_URL"),
    )

    with open(scores_file) as f:
        scores = [json.loads(l) for l in f]
    valid = [s for s in scores if "total" in s]
    valid.sort(key=lambda x: x["total"])
    bottom = valid[:n]

    with open("data/canonical/navworld.jsonl") as f:
        entries = [json.loads(l) for l in f]

    print(f"N2v2: Two-pass rewrite of {len(bottom)} entries (generate → critique → fix)")
    print(f"Score range: {bottom[0]['total']} - {bottom[-1]['total']}")

    semaphore = asyncio.Semaphore(3)  # lower concurrency for 3-call pipeline
    tasks = [rewrite_with_critique(client, s["entry_idx"], entries[s["entry_idx"]], semaphore) for s in bottom]
    results = await asyncio.gather(*tasks)

    successful = [r for r in results if r is not None]
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        for r in successful:
            f.write(json.dumps(r["new_entry"], ensure_ascii=False) + "\n")

    total_in = sum(r["input_tokens"] for r in successful)
    total_out = sum(r["output_tokens"] for r in successful)
    cost = total_in * 3 / 1e6 + total_out * 15 / 1e6

    print(f"\n{'='*60}")
    print(f"Rewritten: {len(successful)}/{len(bottom)}")
    print(f"Had critique fixes: {sum(1 for r in successful if r['had_critique'])}")
    print(f"Avg plan length: {sum(r['plan_len'] for r in successful)//max(len(successful),1)} chars")
    print(f"Cost: ~${cost:.3f}")
    print(f"Output: {output}")

    with open(output + ".index", "w") as f:
        for r in successful:
            f.write(f"{r['entry_idx']}\n")


if __name__ == "__main__":
    asyncio.run(main())
