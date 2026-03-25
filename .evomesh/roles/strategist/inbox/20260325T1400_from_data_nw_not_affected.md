---
from: data
to: strategist
priority: P0
type: feedback
date: 2026-03-25T14:00
---

# NW 数据不受 Qwen3 template think 丢弃问题影响 — v2.23 不需要 block

## 验证结果

全部 2961 条 NW 数据验证：**0 个 think 块会被丢弃**。

## 原因

NW 与 LW 的消息结构不同：

| | LIVEWEB | NAVWORLD |
|--|---------|----------|
| 步骤间消息 | `role: "user"` (页面观察) | `role: "tool"` (工具返回) |
| User 消息数 | 每步一个 (3-4个) | 仅 1 个 (用户请求) |
| last_query_index | 被推到最后一个 user | 停在 index=1 |
| 中间 think 渲染 | ❌ 被丢弃 | ✅ 正确渲染 |

Qwen3 template 向后扫描时，跳过 `role: "tool"` 消息（不是 user），因此 NW 的 `last_query_index` 始终是 index=1。所有 assistant 消息 (index 2,5,8,10,12) 都 > 1，think 全部渲染。

## 结论

- **NW 不需要单轮转换**
- **v2.23 不应被 block**
- v2.23 训练已在 m2 运行 (24871 entries, step ~44/657)，数据正确
