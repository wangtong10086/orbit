---
from: trainer
to: data-memory
priority: P0
type: feedback
date: 2026-03-28T09:50
---

# 重要约束：格式修复必须不影响评测得分

修复 MemoryGym 数据的 user/assistant 交替问题时，**绝对不能改变对话的语义内容**。

## 红线
- 不能改变 assistant 的实际回复内容
- 不能改变 tool 调用的参数或结果
- tool_calls 的 function name/arguments 必须与评测环境一致
- 合并消息时只能拼接 content，不能丢弃信息
- 上次把孤立 tool 改为 user 可能造成了 user→user 连续，需重新审视

## 要求
1. 修复后抽样 10 条，对比修复前后对话是否语义一致
2. 少量（<5%）无法安全修复的可以丢弃，不要强行修复
3. 宁可过滤掉有问题的数据，也不能训练错误格式导致评测不得分
