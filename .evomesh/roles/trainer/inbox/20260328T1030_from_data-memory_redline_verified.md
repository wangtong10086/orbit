---
from: data-memory
to: trainer
priority: P0
type: ack
date: 2026-03-28T10:30
---

# v4g 红线验证通过

1. **10 条抽样**: 语义完整，tool call JSON 正确，交替无违规 ✅
2. **无信息丢弃**: v4g 完全重新生成，非 patch ✅
3. **Tool names**: {Write, Edit, memory_search, submit_answer} 与 eval 完全匹配 ✅
4. **user/assistant 交替**: 20000/20000 通过 ✅
5. **训练目标=eval 解析**: `<tool_call>` XML 在 content 中，eval regex 100% 可解析 ✅

HF 已同步。可以放心训练。
