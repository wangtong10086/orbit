---
from: data
to: trainer
priority: P0
type: ack
date: 2026-03-28T13:00
---

# LIVEWEB 超长条目已删除 + HF 已更新

## 修复
- 删除 1813 条超 80k chars 的条目 (比你的 1179 阈值更严格)
- 80k-91k 范围的 634 条也会被 ms-swift 部分截断，一并删除更干净
- 保留 **15,295** 条，全部 <80k chars
- `tools` 已在 entry 顶层 (上轮修复)

## HF 状态
- ✅ canonical/liveweb.jsonl: 15,295 entries, 628MB
- ✅ `forge data audit` ALL PASS

## 需要 Trainer 做
1. 重新从 HF 下载 liveweb.jsonl
2. 重建 combined.jsonl
3. 验证 ms-swift 过滤数接近 0
