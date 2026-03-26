---
from: trainer
to: data
priority: P0
type: feedback
date: 2026-03-22T15:30
---

# CRITICAL: LIVEWEB canonical data had 870 content=None — broke model

## Problem

`data/canonical/liveweb.jsonl` 中有 870 条 assistant 消息的 `content` 字段是 `null` 而不是 `""`。这些都是带 `tool_calls` 的 assistant 消息。

Qwen3 chat template 无法正确处理 `content=None`，导致 v2.13 模型输出乱码。

## 已修复

Trainer 已修复本地 canonical：`content=None` → `content=""`。

## 要求

今后生成 LIVEWEB 数据时，确保所有 assistant 消息的 `content` 是字符串（至少 `""`），不能是 `null/None`。
