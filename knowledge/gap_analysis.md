# Gap Analysis

**Last updated**: 2026-03-25 12:30 UTC

## v2.23 Results — reasoning-parser trade-off confirmed

| Env | No Parser (best) | With Parser (v2.23) | Delta |
|-----|-----------------|---------------------|-------|
| GAME | 28.21 (v2.20) | 25.79 | -2.42 |
| NW | 42.84 (v2.21) | 19.45 | -23.39 |
| LW | 5.78 (v2.17a) | **12.95** | +7.17 |

## Core Problem

**reasoning-parser helps LW but kills NW.** Cannot use a single sglang config for all envs.

- NW tool_calls still captured as reasoning_content despite think-before-tool_call data fix
- LW single-turn format works — model thinks then uses goto (not click loops)
- GAME thinking adds latency (~10min/task) but score doesn't improve much

## Competitive Position

| Env | Ours (best) | #1 Competitor | Gap | Strategy |
|-----|-------------|--------------|-----|----------|
| GAME | 28.21 | 50.85 | -22.64 | GRPO needed (SFT ceiling) |
| **NW** | **42.84** | 30.72 | **+12.12** | #1 globally — protect |
| LW | 12.95 | 20.26 | -7.31 | Cache fix → ~20+. Close to competitive. |
| SWE-I | never eval'd | 10.00 | ? | 770+ entries, need eval |

## Strategic Options

1. **Eval without reasoning-parser** (GAME ~28, NW ~42, LW ~6) — best NW but LW unusable
2. **Eval with reasoning-parser** (GAME ~25, NW ~19, LW ~13) — LW breakthrough but NW collapse
3. **Fix NW compatibility with reasoning-parser** — root cause unknown, deep analysis needed
4. **Two separate deployments** — user rejected this approach
5. **Focus on cache fix** — LW valid_mean=23.04, fixing cache alone could get LW to 20+ even without reasoning-parser

## Action Items

- [ ] Deep analysis: WHY does reasoning-parser kill NW despite think-before-tool_call data?
- [ ] Deep analysis: GAME per-game breakdown with reasoning-parser (does thinking help any games?)
- [ ] Stooq cache fix (infra)
- [ ] SWE-I eval (never done)
- [ ] GAME new data from user/data-game
