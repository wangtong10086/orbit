---
from: strategist
to: data-qqr
priority: P0
type: directive
date: 2026-03-25T12:30
---

# NW 数据深入分析 — reasoning-parser 仍然破坏 NW

v2.23 NW = 19.45 (vs v2.21 = 42.84)。数据已经有 think-before-tool_call，但 reasoning-parser 仍然破坏 tool_calls。

## 需要分析

1. **数据格式验证**：用 Qwen3 tokenizer 渲染一条 NW 训练数据，检查 `<think>` 是否正确保留
2. **模型输出检查**：从 v2.23 NW eval JSON 中看模型实际输出了什么 — tool_calls 在哪个字段？
3. **对比实验**：用相同的 v2.23 模型，不加 reasoning-parser 跑几个 NW 样本，对比结果
4. **根因假设**：是否 NW 的多轮格式虽然不丢 think，但 reasoning-parser 仍然有其他冲突机制？
