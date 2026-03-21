---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-21T05:00
---

# 紧急：评测必须加 CHUTES_API_KEY

## 发现
我们所有 NAVWORLD eval 只跑了 code score (50分)，**丢了 LLM score (50分)**！

NAVWORLD 评测内置 Chutes API：
```python
# repos/affinetes/environments/qqr/llm_validator.py
base_url = "https://llm.chutes.ai/v1"
api_key = os.getenv("CHUTES_API_KEY")
```

## 立即执行

1. **设置环境变量**: `export CHUTES_API_KEY=<key>` (从 .env 或用户获取)
2. **重跑 v2.4a eval** (我们最佳 GM 模型) — 这次带 CHUTES_API_KEY
3. NAVWORLD 分数可能从 7.71 跳到 15-20+（之前只有 50% 的分数）

## GAME 零分修复

零分游戏根因确认：think block 含裸数字干扰 parser。

**修复方案**：让 data-game 重新生成所有 think block，替换数字为文字：
- "3-step" → "multi-step"
- "5 possible moves" → "several possible moves"
- 确保 think 去除后只剩纯数字 action ID

这两个修复的预期影响：
- NAVWORLD: 7.71 → **15-25** (补上 LLM 50分)
- GAME: 26 → **35-45** (零分游戏开始得分)
