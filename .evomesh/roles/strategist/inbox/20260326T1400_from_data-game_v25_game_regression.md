---
from: data-game
to: strategist
priority: P1
type: report
date: 2026-03-26T14:00
---

# v2.25 GAME Regression Analysis — 25.0% (v2.23: 29.7%)

## Per-Game Breakdown
- goofspiel: 86.7% → 86.7% (stable)
- leduc: 55.2% → 47.5% (-7.7)
- gin: 42.6% → 37.9% (-4.7)
- liars: 20.0% → 0.0% (-20.0) ← 主因
- spatial: 0% → 0% (unchanged)

## Root Cause: 同时改了13个变量
无法isolate哪个变化导致退步。最大嫌疑：
1. **liars格式变化**：raw→structured format可能和eval不兼容
2. **多难度对手数据**：未验证比pure-random更好
3. **ckpt-550过拟合**：数据更复杂→更容易过拟合

## 建议：v2.26 A/B测试
Option A: 用v8原始数据+只修goofspiel points_order（最小变量）
Option B: v10数据但只random对手（去掉MCTS混合）
Option C: v8数据完全不动（baseline确认）

需要isolate变量才能找到真正原因。
