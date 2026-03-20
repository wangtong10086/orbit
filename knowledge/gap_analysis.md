# Gap Analysis

**Last updated**: 2026-03-20 11:15 UTC (Strategist loop 38)

## Training History

| Ver | GAME | NAVWORLD | LIVEWEB | SWE | Loss | Key Change |
|-----|------|----------|---------|-----|------|-----------|
| v2.1 | 25.74 | 8.47 | — | — | 0.156 | Baseline, seq=8192, 1-GPU |
| v2.2 | 26.04 | 6.10 | 6.83 | FAIL | 0.224 | seq=16384, 4-GPU DDP |
| v2.3 | ~26* | **1.51** | **7.50** | skip | ~0.18 | GAME v5, *GAME eval running 44/100 |
| v2.4 | — | — | — | — | — | APPROVED: remove qwen-max NW + SWE-SYNTH, seq=8192 |

## v2.3 Results (2/3 complete, GAME running)

| Env | Score | Change vs v2.2 | Analysis |
|-----|-------|----------------|----------|
| NAVWORLD | **1.51** | -4.59 ⚠️ | Severe regression. 9% nonzero (was 37%). Model spams poi_search only. |
| LIVEWEB | **7.50** | +0.67 | Marginal. Format fix had minimal impact. |
| GAME | ~26 est* | ~flat | 44/100 running. Zero-tier still 0 but root cause = **eval parsing, not SFT inability** |

### NAVWORLD Regression Root Cause
- qwen-max 5-template data (2205/2624 = 84%) teaches model to only use poi_search
- seq=16384 correlates with decline (v2.1 at 8192 = 8.47)
- **Fix in v2.4**: removed ALL 2205 qwen-max → canonical now 919 pure Claude+GPT-5.4

### GAME Zero-Tier Root Cause (NEW — from data-game analysis)
- **NOT SFT-unlearnable** — root cause is **eval parsing failure**
- Coordinate games (hex `12→c3`, clobber `33→c6b6`): model reasoning numbers confuse parser
- Board games use raw ASCII grids — model can't reason about spatial positions
- **Fix**: GPT-5.4 distillation teaches clean output format (in progress: liars_dice 894, leduc 357, goofspiel 153, hex 38, clobber 3)

## Live Leaderboard (Block 7784716)

| Rank | Miner | GAME | NAVWORLD | SWE | LIVEWEB |
|------|-------|------|----------|-----|---------|
| 1 | wisercat | 45.60 | 23.36 | 45.00 | 18.64 |
| 2 | vera6 | 48.85 | 21.94 | 31.00 | 18.10 |
| 3 | AnastasiaF | 47.74 | 17.87 | 37.37 | 23.21 |
| 6 | coffie3 | 37.90 | 21.01 | 47.00 | 15.39 |
| **v2.3** | **ours** | **~26** | **1.51** | **skip** | **7.50** |

## v2.4 Plan (APPROVED)

| Env | Count | Change vs v2.3 | Expected Impact |
|-----|-------|----------------|-----------------|
| GAME | 3631 | unchanged | stable ~26 |
| NAVWORLD | **919** | cleaned (was 2624), 100% diverse tools | **target 8-15** (back to v2.1+ level) |
| LIVEWEB | 397 | +9 | stable ~7.5 |
| SWE-SYNTH | **0** | removed (deprecated) | N/A |
| **Total** | **4947** | -2679 | quality >> quantity |

Key config: **seq=8192** (reverted from 16384), batch=2, grad_accum=2

## Rank-Jump ROI (priority order)

1. **NAVWORLD** (1.51 vs #6=21.01, gap=19.5): v2.4 primary target. Clean data + seq=8192
2. **GAME zero-tier** (~26 vs #6=37.90, gap=12): GPT-5.4 distillation fixing parsing issue
3. **LIVEWEB** (7.50 vs #6=15.39, gap=7.9): need more data + plugin diversity
4. **SWE-Infinite** (0 vs #6=47): data-swe building pipeline, 9 trajectories so far

## Action Items

- [x] v2.3 NAVWORLD/LIVEWEB eval complete
- [ ] v2.3 GAME eval (44/100 running)
- [x] v2.4 APPROVED (clean data + seq=8192)
- [x] NAVWORLD qwen-max removed (919 clean entries)
- [ ] v2.4 training launch (after v2.3 GAME completes)
- [ ] GAME GPT-5.4 distillation completion (~1190 target)
- [ ] data-swe trajectory collection (9/~138 target)
