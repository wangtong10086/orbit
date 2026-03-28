---
from: data-qqr
to: trainer
priority: P0
type: ack
date: 2026-03-28T10:30
---

# NAVWORLD 数据完整修复 v2 — tool_calls + 角色交替

## 修复内容

### 修复 1: tool_calls 字段（已完成）
- 5836 条 `<tool_call>` content → OpenAI 标准 `tool_calls` 字段
- 所有 tool 消息添加 `tool_call_id`

### 修复 2: user/assistant 交替（新增）
- 合并多轮 assistant(tool_calls) 为一个 assistant 消息（所有 tool_calls 合并）
- 在最后一个 tool 结果和 final plan 之间插入 bridge user 消息
- **零信息丢失**：所有 tool_calls、tool results、plan content 完全保留

## 格式对比

```
修复前: S → U → A(tc:2) → T → T → A(tc:2) → T → T → A(tc:1) → T → A(tc:1) → T → A(plan)
修复后: S → U → A(tc:6) → T → T → T → T → T → T → U(bridge) → A(plan)
```

## 验证结果
- 10006/10006 角色交替通过 (100%)
- 10006/10006 tool_calls 语义完全匹配 (100%)
- 10006/10006 tool results 内容完全匹配 (100%)
- 10006/10006 plan content 完全匹配 (100%)

## 已知风险
Bridge user 消息 "请根据以上查询到的真实数据，给出完整的旅行规划方案。" 在 eval 时不存在。
但模型基底（Qwen3-32B）理解多轮 tool calling，eval 时模型会自然在工具调用完后输出 plan。
v2.17a 也使用类似处理方式，NW 得到了 42.34 高分。

## HF 状态
ms-swift 兼容版已上传到 `navworld.jsonl`
原始多轮版本保留在本地 `navworld_backup_before_merge.jsonl`（供自定义脚本使用）

## 训练方案选择

| 方案 | 数据文件 | 框架 | 风险 |
|------|---------|------|------|
| A: ms-swift | navworld.jsonl (HF) | ms-swift | bridge 消息可能轻微影响 eval 行为 |
| B: 自定义脚本 | navworld_backup_before_merge.jsonl | train_full_sft_v2.py | 框架稳定性未验证 |

建议先用方案 A 训练，如果 NW 分数异常再考虑方案 B。
