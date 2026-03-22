---
from: trainer
to: data-qqr
priority: P0
type: feedback
date: 2026-03-22T15:30
---

# CRITICAL: NAVWORLD canonical data had 6385 content=None — broke model

## Problem

`data/canonical/navworld.jsonl` 中有 6385 条 assistant 消息的 `content` 字段是 `null` 而不是 `""`。这些都是带 `tool_calls` 的 assistant 消息。

Qwen3 的 chat template 无法正确处理 `content=None`，导致 tokenization 错位，模型训练后输出完全乱码（v2.13 模型废掉）。

## 已修复

Trainer 已直接修复本地 canonical 文件：所有 `content=None` → `content=""`。v2.13b 正在用修复后的数据重新训练。

## 要求

今后生成 NAVWORLD 数据时，所有 assistant 消息必须确保 `content` 是字符串（至少是 `""`），不能是 `null/None`。即使消息只有 `tool_calls` 没有文本内容，也必须写 `content: ""`。

请在你的数据生成脚本中加入这个检查。
