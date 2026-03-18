# Gap Analysis

**Last updated**: 2026-03-18 15:30 UTC
**Status**: PRE-DEPLOYMENT — v2 training in progress, ETA ~19:15 UTC

## Live Leaderboard (Block 7772891)

| Rank | Miner | GAME | NAVWORLD | SWE-SYNTH | LIVEWEB | Weight |
|------|-------|------|----------|-----------|---------|--------|
| 1 | affshoot | 50.03 | 15.72 | 53.19 | 19.08 | 0.508 |
| 2 | vera6 | 50.59 | 25.12 | 27.00 | 19.11 | 0.254 |
| 3 | wisercat | 47.06 | 23.88 | 39.39 | 18.07 | 0.127 |
| 4 | AnastasiaFantasy | 40.84 | 24.84 | 40.00 | 16.53 | 0.063 |
| 5 | RLStepone | 49.37 | 21.88 | 39.00 | 16.31 | 0.032 |
| 6 | coffie3 | 41.56 | 21.69 | 46.00 | 16.38 | 0.016 |

**Changes from Block 7771839**: wisercat NEW at #3, vera6 ↑#2, AnastasiaFantasy ↓#4, coffie3 NEW at #6.

## Gap Table (vs #1 affshoot)

| Env | #1 Score | Competitor Range | Our v11 | Gap to #1 | Priority |
|-----|----------|-----------------|---------|-----------|----------|
| GAME | 50.03 | 40.8-50.6 | 22.6 | -27.4 | P1 |
| NAVWORLD | 15.72 | 15.7-25.1 | 5.7 | -10.0 | **P0** |
| SWE-SYNTH | 53.19 | 27.0-56.6 | ~31 | -22.2 | P1 |
| LIVEWEB | 19.08 | 14.5-19.1 | ~24 | +4.9 | Maintain |

## 4-env GM Analysis

**Competitor GMs** (approximate):
- affshoot: (50.03 × 15.72 × 53.19 × 19.08)^(1/4) ≈ 30.1
- vera6: (50.59 × 25.12 × 27.00 × 19.11)^(1/4) ≈ 29.1
- wisercat: (47.06 × 23.88 × 39.39 × 18.07)^(1/4) ≈ 30.0

**Our v2 scenarios**:

| Scenario | GAME | NAVWORLD | SWE-SYNTH | LIVEWEB | 4-env GM |
|----------|------|----------|-----------|---------|----------|
| Conservative | 25 | 6 | 15 | 18 | ~13.9 |
| Target | 30 | 8 | 20 | 20 | ~17.3 |
| Optimistic | 35 | 10 | 25 | 22 | ~21.4 |

**NAVWORLD remains the GM killer** — at 5.7, it drags everything down.

## ROI Analysis (updated 17:01 UTC — incorporates data quality findings)

| Env | Current → Target | 4-env GM Impact | Effort | ROI | Root Cause |
|-----|-----------------|-----------------|--------|-----|------------|
| NAVWORLD | 5.7 → 18 | **+8.2 GM** | High (data diversity first) | **Highest** | **5-template data** — SFT天花板是数据多样性问题 |
| GAME | 22.6 → 40 | +3.8 GM | Medium (gin_rummy bot broken) | High | gin_rummy bot只有1.8%胜率+单模板thinking |
| SWE-SYNTH | 31 → 40 | +1.4 GM | Low (seq=8192) | High | — |
| LIVEWEB | 24 → 24 | 0 | None | N/A | — |

## Data Quality Findings (2026-03-18 17:00 UTC)

### NAVWORLD: 5-Template Root Cause (CRITICAL)
- All 2248 entries from **5 query templates**, each ~448 entries
- Only **5 tool-call sequences**, **10 origin cities**, **~25 destinations**
- 1,331 reused tool call IDs across entries — parametric variation of 5 conversations
- **SFT天花板根因**: model learns 5 recipes, not general reasoning
- **Fix**: expand to 20+ query types BEFORE doing RL (RL on 5-template data = memorizing 5 patterns faster)

### GAME: gin_rummy Bot Data Unusable
- v3 staged 440 gin_rummy entries: **ALL REJECTED** — single-template thinking, 1.8% win rate
- v3 effective keep: only 168/690 (goofspiel 150 + leduc 18)
- Canonical data difficulty: 79.7% MEDIUM+HARD (2105/2641) — good base for Phase 3
- **Fix**: rebuild gin_rummy bot (game-state-aware thinking, real strategy, >50% win rate)

## Rank-Jump Opportunities

- **NAVWORLD**: field compressed (15.7-25.1). Even 15+ puts us mid-pack. **But needs data diversity first, not just method change.**
- **GAME**: field compressed (40.8-50.6). gin_rummy fix + GRPO could close gap significantly.
- **SWE-SYNTH**: widest spread (27.0-56.6). deepresearch001 at 55.56 proves >50 is achievable.

## Action Items

- [x] GAME data recovered + bot data generated (2641 entries)
- [x] v2 experiment approved and RUNNING (ETA ~19:15 UTC)
- [x] NAVWORLD quality analysis — 5-template root cause identified
- [x] GAME v3 rejection sampling — 168/690 approved, 522 rejected
- [x] GAME difficulty profiling — 79.7% MEDIUM+HARD
- [x] Contamination check script designed (D4)
- [ ] **D5: Fix gin_rummy bot pipeline** (Data agent — in progress)
- [ ] **D6: NAVWORLD diversity expansion plan** (Data agent — in progress)
- [ ] v2 eval → diagnose per-env performance (GAME + NAVWORLD)
- [ ] If GM<20 → v2a iteration (fix weakest env, use quality-filtered data)
- [ ] Phase 3: NAVWORLD data diversity expansion THEN GRPO
