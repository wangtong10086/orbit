# v2.28 数据过滤分析 — ms-swift 过滤了 17137 条 (19.6%)

## 概要

| 环境 | 原始数据 | 训练数据 | 过滤数 | 过滤率 |
|------|---------|---------|-------|--------|
| GAME | 38663 | ~38663 | 0 | 0% |
| LIVEWEB | 17108 | ~17108 | 0 | 0% |
| NAVWORLD | 10006 | ~10006 | 0 | 0% |
| SWE-INFINITE | 1555 | ~1555 | 0 | 0% |
| **MemoryGym** | **20000** | **~2863** | **~17137** | **85.7%** |
| **总计** | **87332** | **70195** | **17137** | **19.6%** |

## 根因：MemoryGym 数据格式不兼容 ms-swift

### ms-swift 报错
```
AssertionError: response_role: "user"
[WARNING:swift] 👆👆👆There are errors in the dataset, the data will be deleted
```

### MemoryGym 数据格式问题

典型 MemoryGym 样本结构：
```
[system] You are participating in a memory management evaluation...
[user]   Tool results: [Write] Stored (id=xxx). 14 writes remaining...    ← 问题在这里
[assistant] OK.
[user]   Next task...
[assistant] ...
```

**问题**: 第一个 `user` 消息的内容是 "Tool results: ..." —— 这实际上是工具返回结果，不是用户查询。ms-swift 的模板解析器将其识别为 tool response，但角色是 `user` 而非 `tool`，导致 `response_role: "user"` 断言失败。

### MemoryGym 消息模式分布
| 模式 | 数量 | 占比 |
|------|------|------|
| system-user-assistant-user-assistant-user-assistant... (7+ msgs) | 11922 | 59.6% |
| system-user-assistant-user-assistant (5 msgs) | 7188 | 35.9% |
| system-user-assistant (3 msgs) | 890 | 4.5% |

大部分 7+ 消息的样本以 "Tool results:" 开头 → 被过滤。短样本（3 msgs）可能没有 tool result 前缀 → 保留。

## 其他环境数据状态（正常）

- **GAME** (38663): 无 tool_calls，无 tools field，格式标准 → 0% 过滤
- **LIVEWEB** (17108): 有 tool_calls + tool role messages → ms-swift 正确处理
- **NAVWORLD** (10006): 4170 有 tool_calls，全部有 tool role → ms-swift 正确处理
- **SWE-INFINITE** (1555): 格式标准 → 0% 过滤

## 修复建议

### MemoryGym 数据修复（Data 角色负责）

1. **将 "Tool results:" user 消息改为 `tool` 角色**
   - 如果前一个 assistant 消息有 `tool_calls`，则后续的 "Tool results:" 应该是 `role: "tool"` 而非 `role: "user"`

2. **或者去掉 tool result 前缀，合并为普通 user 消息**
   - 将 "Tool results: [Write] Stored..." 改为普通的 user 描述

3. **验证方法**: 修复后用 ms-swift 测试：
   ```bash
   swift sft --model Qwen/Qwen3-32B --dataset fixed_memorygym.jsonl --train_type full --deepspeed zero3 --max_length 32768 --num_train_epochs 0.001
   ```
   检查 `train_dataset` 的 `num_rows` 是否接近输入行数。

## 影响

当前 v2.28 训练使用 70195 条数据（不含大部分 MemoryGym）。如果 MemoryGym 对成绩有重要影响，修复后需要重新训练。
