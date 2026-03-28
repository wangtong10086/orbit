# v2.28 数据过滤分析 V2 — 32690 条被过滤 (37.4%)

## 概要

| 环境 | 总数 | 预计保留 | 过滤数 | 过滤率 |
|------|------|---------|--------|--------|
| GAME | 38663 | ~38663 | ~0 | 0% |
| MemoryGym | 20000 | ~3374 | ~16626 | **83%** |
| LIVEWEB | 17108 | ~11050 | ~6058 | **35%** |
| NAVWORLD | 10006 | ~0 | ~10006 | **100%** |
| SWE-INFINITE | 1605 | ~1605 | ~0 | 0% |
| **总计** | **87382** | **54692** | **32690** | **37.4%** |

## 过滤原因分析

### 原因 1: tool 消息前无 tool_calls（26632 条）

ms-swift 要求严格的对话流：
```
assistant: {content: "...", tool_calls: [{id: "xxx", function: {...}}]}  ← 必须有 tool_calls
tool: {content: "result", tool_call_id: "xxx"}  ← 对应 tool_call_id
```

**NAVWORLD (10006 条, 100% 被过滤)**:
- 所有 NW 数据有 `tool` role 消息（工具调用结果）
- 但前面的 `assistant` 消息没有 `tool_calls` 字段
- ms-swift 无法匹配 tool response → 全部过滤

**MemoryGym (16626 条, 83%)**:
- data-memory 修复了 `role: "user"` → `role: "tool"`
- 但没有在前面的 `assistant` 消息里加 `tool_calls` 字段
- ms-swift 看到 `tool` response 但找不到对应的 `tool_calls` → 过滤

### 原因 2: 超长序列（81 条）
- LIVEWEB: 81 条超过 130k chars（tokenize 后超过 32768 tokens）
- ms-swift 截断或丢弃

### 原因 3: 其他 ms-swift 内部过滤（~5977 条）
- LIVEWEB 剩余过滤可能是 tool_calls 格式问题
- 需进一步调查

## 修复方案

### NAVWORLD 修复（Data-QQR 角色）
每个包含 `role: "tool"` 的样本，在前面的 `assistant` 消息中添加 `tool_calls` 字段：

```json
// 修复前
{"role": "assistant", "content": "I'll search for restaurants nearby."}
{"role": "tool", "content": "{\"results\": [...]}"}

// 修复后
{"role": "assistant", "content": "I'll search for restaurants nearby.",
 "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "search_poi", "arguments": "{...}"}}]}
{"role": "tool", "content": "{\"results\": [...]}", "tool_call_id": "call_1"}
```

### MemoryGym 修复（Data-Memory 角色）
同样的问题 — `role: "tool"` 消息前的 `assistant` 缺少 `tool_calls`。

### LIVEWEB 调查
5977 条额外过滤需要调查是否也是 tool_calls 格式问题。

## 验证方法
修复后在 m3 上测试：
```bash
# 快速验证
NPROC_PER_NODE=1 swift sft --model /data/models/Qwen3-32B \
  --dataset /data/datasets/fixed_data.jsonl \
  --train_type full --deepspeed zero3 --num_train_epochs 0.001
# 检查 train_dataset num_rows 是否接近输入行数
```
