---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-21T05:30
---

# P0: 用 Chutes API 跑完整评测（含 LLM 分数）

我们所有 NAVWORLD eval 都缺了 LLM 评分（50/100分）。必须立刻修复。

## 操作

1. **设置环境变量**:
   ```bash
   export CHUTES_API_KEY=<从.env或用户获取>
   ```
   eval 代码内置 Chutes: `https://llm.chutes.ai/v1`

2. **用 v2.4a 模型重跑 NAVWORLD eval**（我们最佳 GM 模型）
   - v2.4a HF: `monokoco/affine-qwen3-32b-v2.4a`
   - 这次应该能看到满分 100 的 NAVWORLD 分数（之前只有 code 50 分）

3. **同时跑 SWE-INFINITE eval**
   - SWE 从未被评测过
   - 983 条真实轨迹数据已训练在 v2.1-v2.3 中

4. **如果 CHUTES_API_KEY 不在 .env 中，请向用户索取**

## 为什么紧急

我们做了 8 个版本的训练迭代，但可能一直在看错误的分数。NAVWORLD 7.71 可能只是 50 分满分的表现——加上 LLM 50 分后可能是 15+。在知道真实分数之前，任何训练优化都是盲目的。

## 额外：GAME 零分游戏

已确认：100% 解析成功，0% 策略能力。不是格式问题。
- hex/clobber bot 胜率只有 55-59%，训练数据本身策略就弱
- 需要更强 bot 或更多 GPT-5.4 蒸馏
- data-game v6 已大幅提升 think diversity，v2.7 是第一次用这些数据
