# Gap Analysis

**Last updated**: 2026-03-26 10:00 UTC

## Best Scores & Competitive Position

| Env | Our Best | Model | #1 Competitor | Gap | Rank |
|-----|----------|-------|--------------|-----|------|
| GAME | 29.70 | v2.23 | 50.18 (wisercat) | -20.48 | 7/7 |
| **NW** | **42.84** | v2.21 | 34.86 (EdmondMillion) | **+7.98** | **1/7** |
| LW | 17.68 | v2.23 | 19.35 (luis1027) | -1.67 | ~5/7 |
| SWE-I | never eval'd | — | 9.18 | ? | ? |

## v2.24 Results — ALL REGRESSED

| Env | v2.24 | v2.23 | Delta |
|-----|-------|-------|-------|
| GAME | 24.40 | 29.70 | **-5.30** |
| NW | 19.57 | 34.88 | **-15.31** |
| LW | 12.69 | 17.68 | **-4.99** |

### Root Cause Analysis

**v2.24 data**: GAME 8747(v8) + NW 3865 + LW 6892 + SWE-I 804 = 20308

1. **GAME regression (-5.30)**: Used old v8 data (13 known bugs: goofspiel config, liars format, gin knock 0%). v10 fixes not merged. Poisoned model.
2. **NW collapse (-15.31)**: NW was at 19.0% — ON threshold — yet collapsed to 19.57. **The 19% rule is insufficient.** NW best scores came with smaller total datasets (~8000-13000). v2.24 at 20308 may be too diluted, or buggy GAME v8 data cross-contaminated NW.
3. **LW regression (-4.99)**: 31 cache errors (vs 12). Tools fix should have helped but cache degradation masked it.

### CRITICAL: NW Proportion Rule WRONG

| Version | NW % | NW Score | Total Data | Notes |
|---------|------|----------|-----------|-------|
| v2.17a | 19.7% | **42.34** | 8401 | Small dataset, no SWE-I |
| v2.21 | 22.2% | **42.84** | 13344 | Best NW ever |
| v2.23 | 11.9% | 34.88 | 24873 | Large dataset, LW 12054 |
| **v2.24** | **19.0%** | **19.57** | 20308 | **Buggy GAME v8 data** |

NW proportion alone doesn't explain performance. Other factors matter:
- **GAME data quality**: buggy GAME data may cross-contaminate
- **Total dataset size**: best NW with 8000-13000 total, not 20000+
- **Checkpoint position**: ckpt-500/605, may not be optimal

## v2.25 Status — TRAINING

GAME v10 9966 + NW 4148 + LW 8816 + SWE-I 853 = 23783

Key changes vs v2.24:
- GAME v10 (13 bug fixes, rule-based think) — fixes root cause #1
- LW 8816 with tools fix — more data than v2.24's 6892
- NW 4148 (17.4%) — below 19% but GAME data quality may be more important

Risk: if GAME v8 was the root cause of v2.24's NW collapse, v2.25 with GAME v10 should recover. If total data size is the issue, 23783 is even larger.

## Confirmed Rules (updated)

1. **NO reasoning-parser** — A/B tested, hurts all envs
2. **Checkpoint ~80-85%** — late overfitting confirmed
3. ~~**NW ≥19% of mix**~~ — **DISPROVED by v2.24** (19% → still collapsed). Data quality matters more than proportion.
4. **LW single-turn format** — 5.78→17.68, no parser needed
5. **GAME data quality critical** — buggy GAME data (v8) may cross-contaminate ALL envs
6. **LW tools fix** — not yet validated (v2.24 had cache errors masking improvement)
7. **Final save corruption** — always merge from numbered checkpoint
