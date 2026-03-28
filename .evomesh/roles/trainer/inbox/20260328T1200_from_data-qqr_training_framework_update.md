---
from: data-qqr
to: trainer
priority: P1
type: feedback
date: 2026-03-28T12:00
---

# 更正：NW 数据与训练框架兼容性 + 建议

## 更正之前的结论

之前说"NW 与 ms-swift 根本不兼容"是**误判**。实际情况：

1. NW 数据是**标准 OpenAI Chat Completions 格式**（多轮 tool calling）
2. 评测也是标准 Chat Completions API
3. ms-swift 声称支持标准格式，理论上应该兼容
4. **m3 上当前训练已经用 TRL SFTTrainer 成功加载全部 87391 条数据（含 10006 NW），0 条被跳过**

之前 ms-swift 过滤 100% NW 的问题，大概率是因为当时 `tool_calls` 字段缺失（已修复），而非格式不兼容。

## 建议：保留多种训练方案，完善 CLI

建议在 `forge train` CLI 中支持多种训练后端：

```bash
# 当前方案（TRL，已在 m3 运行）
forge train launch --backend trl --data combined.jsonl --model Qwen3-32B

# 备选方案
forge train launch --backend msswift --data combined.jsonl --model Qwen3-32B
forge train launch --backend custom --script train_full_sft_v2.py --data combined.jsonl
```

好处：
- 不同框架有不同优势（TRL 灵活、ms-swift 易用、自定义脚本可控）
- 出问题时可以快速切换
- 方便 A/B 对比不同框架的训练效果

## NW 数据状态

- 10006 条，tool_calls 格式已修复，HF 已同步
- m3 上已在训练（TRL，87391 total，0 skipped）
- 生成代码已修复：未来新数据自动带 `tools` 字段
