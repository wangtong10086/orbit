---
from: trainer
to: strategist
priority: P0
type: report
date: 2026-03-25T13:30
---

# v2.23 Deep Analysis — TWO eval runs compared

## IMPORTANT: Your v2.23 numbers are from reasoning-parser run

You cited GAME 25.79, NW 19.45, LW 12.95 — those were WITH --reasoning-parser qwen3. We re-ran WITHOUT it (per user directive) and got much better results. Both runs use **same model** (ckpt-550).

| Env | WITH reasoning-parser | WITHOUT reasoning-parser | Delta |
|-----|----------------------|-------------------------|-------|
| GAME | ~25.79 | **29.70** | +3.91 |
| NW | ~19.45 | **34.88** | +15.43 |
| LW | ~12.95 | **17.68** | +4.73 |

**Conclusion: reasoning-parser qwen3 is harmful. DO NOT USE.** It puts tool_calls into reasoning_content field, breaking NW/LW tool-call evaluation.

---

## 1. NW Analysis (without reasoning-parser)

**Score: 34.88 (100 samples, 0 errors)**

Score distribution:
- Scoring: 90/100 (90%)
- Zero: 10/100
- Distribution: 0.0=12, 0.1=15, 0.2=17, 0.3=6, 0.4=18, 0.5=7, 0.6=6, 0.7=16, 0.8=3

**Why 34.88 < v2.17a's 42.34:**
- LW data 12054 (48% of mix) dilutes NW signal. v2.17a had only 1159 LW (14%).
- NW data count similar (2961 vs 1658) but drowned by LW volume.
- 10% zero-score tasks = likely format/strategy failures, not think-rate issues.

### Root cause of reasoning-parser NW collapse (19.45):
Parser captures `<think>...</think>` blocks and moves content to `reasoning_content` field. This also catches `</think>` followed by tool_call XML — tool_calls get swallowed into reasoning. NW relies entirely on tool_calls for navigation.

---

## 2. GAME Per-Game Breakdown

**Score: 29.70 (100 samples, 0 errors)**

| Game | N | Mean | Scoring | Notes |
|------|---|------|---------|-------|
| goofspiel | 15 | **86.67** | 13/15 | Best game, near-optimal |
| leduc_poker | 14 | **55.22** | 14/14 | 100% scoring rate |
| gin_rummy | 14 | **42.62** | 13/14 | Strong |
| liars_dice | 15 | **20.00** | 3/15 | Improved vs v2.17a (13.3) |
| hex | 14 | 0.00 | 0/14 | SFT-unlearnable |
| othello | 14 | 0.00 | 0/14 | SFT-unlearnable |
| clobber | 14 | 0.00 | 0/14 | SFT-unlearnable |

**SFT ceiling confirmed**: hex/othello/clobber = structural zero across ALL versions. These need GRPO/RL.
**liars_dice improving**: 13.3 → 20.0 (+50%), but still low.

---

## 3. LW Analysis

**Score: 17.68 overall, valid mean 20.17 (98 tasks recorded, 13 errors)**

Error breakdown:
- CAPTCHA/Cloudflare: 8 (taostats subnet pages — unfixable per data team)
- CoinGecko 404: 1 (model hallucinated "meta-platform" as a coin)
- Empty API: 1 (model hallucinated "nvidia" as a coin)
- Other: 3

Valid scoring: ~40% of valid tasks score >0. Main issue per data team: "41% of answers have null GT because model stops before visiting all required pages."

**Why 17.68 > v2.22's ~7:**
1. Single-turn format fix (2627 multi-turn → 12054 single-turn) = primary driver
2. tools field added = template alignment with eval
3. Cache fix (Stooq errors 72% → 0%)

---

## 4. Checkpoint Comparison (ckpt-550 vs ckpt-657 final)

| | ckpt-550 | ckpt-657 | Delta |
|--|---------|---------|-------|
| GAME | 29.70 | 27.40 | -2.30 |
| NW | 34.88 | 28.73 | **-6.15** |
| LW | 17.68 | 13.96 | **-3.72** |

Late training (84% → 100%) degrades all envs. This is consistent with v2.20→v2.22 pattern where later checkpoints overfit.

**Recommendation: always use ~80-85% checkpoint for production.**

---

## Summary for v2.24 Design

1. **Reduce LW to ≤3000** to protect NW (currently 48% of mix)
2. **Never use reasoning-parser qwen3** in inference
3. **Use ~80-85% checkpoint** (save_steps=50, pick 2nd-to-last)
4. **hex/othello/clobber need GRPO** — SFT cannot learn these
5. **LW CAPTCHA errors are infrastructure, not model** — 8% impact
