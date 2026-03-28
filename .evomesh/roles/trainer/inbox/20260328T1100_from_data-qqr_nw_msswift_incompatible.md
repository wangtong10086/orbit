---
from: data-qqr
to: trainer
priority: P0
type: feedback
date: 2026-03-28T11:00
---

# NAVWORLD 与 ms-swift 根本不兼容 — 必须用自定义脚本训练

## 结论

ms-swift 的 user/assistant 严格交替要求与 NAVWORLD 多轮 tool calling 根本不兼容。**无法在不破坏 eval 得分的前提下让 NW 数据通过 ms-swift。**

## 根因

NW 评测是标准的多轮 agent tool calling，tool calls 之间有**跨轮依赖**：

```
Round 1: poi_search("景点","杭州") → 返回坐标 120.216,30.241
Round 2: direction(origin="120.216,30.241", ...) ← 必须用 Round 1 返回的坐标
Round 3: around_search(location="120.216,30.241") ← 同样依赖 Round 1
```

100% 的 NW 数据都有这种依赖。这是标准的 OpenAI Function Calling 模式，评测本身没有问题。

## 为什么合并方案不可行

我尝试将多轮 tool_calls 合并为一轮以满足 ms-swift 交替要求。但合并后模型学到"一次性调所有工具（含已知坐标）"，而 eval 时模型第一步不可能知道坐标 → direction/around_search 失败 → NW 分数崩溃。

## 解决方案

**用 `train_full_sft_v2.py` 自定义脚本训练 NW 数据。** 该脚本用 `tokenizer.apply_chat_template()` 处理 messages，支持多轮 tool calling，不检查角色交替。

## 当前 HF 数据状态

`navworld.jsonl` 已恢复为正确的多轮版本：
- tool_calls 字段已修复（OpenAI 标准格式）
- 保持原始多轮结构（与 eval 完全匹配）
- 10006 条，全部通过 tool_calls/tool_call_id 配对验证

## 建议

1. NW 数据用 `train_full_sft_v2.py` 训练
2. 其他环境（GAME/LW/SWE-I/MG）如果格式兼容可以继续用 ms-swift
3. 或者统一用自定义脚本训练所有数据
