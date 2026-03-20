# Gap Analysis

**Last updated**: 2026-03-20 06:30 UTC (Strategist loop 19)
**Status**: v2.2 EVAL COMPLETE. v2.3 APPROVED, awaiting launch. v2.4 DRAFTING.

## v2.2 Final Results

| Env | v2.1 | v2.2 | Change | vs #6 | vs #1 |
|-----|------|------|--------|-------|-------|
| GAME | 25.74 | **26.04** | +0.3 | -11.9 (37.90) | -19.6 (45.60) |
| NAVWORLD | 8.47 | **6.10** | -2.4 ⚠️ | -14.9 (21.01) | -17.3 (23.36) |
| SWE-SYNTH | — | **FAILED** | Docker missing | — (44.00) | — (45.00) |
| LIVEWEB | — | **6.83** | first score! | -8.6 (15.39) | -11.8 (18.64) |

### v2.2 Key Findings
1. **GAME flat** — 3 learnable games at 45-87%, 4 zero-tier unchanged. Data quality not the issue for learnable games; zero-tier games are the opportunity.
2. **NAVWORLD regressed** (8.47→6.10) — despite replacing low-QQR qwen-max with Claude Sonnet. Possible cause: seq=16384 diluting, or same-family qwen-max data (84% of mix) hurting generalization.
3. **LIVEWEB scoring!** — 6.83 with 32 cache errors. Non-zero rate 16%, avg 0.427 when scoring. Format fix in v2.3 should help.
4. **SWE-SYNTH blocker** — Docker image not on machine. Must fix before v2.3 eval.

### v2.2 GAME Per-Game Breakdown
| Game | Score | Non-zero | Status |
|------|-------|----------|--------|
| goofspiel | 86.7% | 13/15 | Strong |
| leduc_poker | 48.1% | 13/14 | Solid |
| gin_rummy | 45.1% | 14/14 | Solid |
| **clobber** | **0.0%** | 0/14 | Zero — v2.3 has 469 entries |
| **hex** | **0.0%** | 0/14 | Zero — v2.3 has 452 entries |
| **liars_dice** | **0.0%** | 0/15 | Zero — v2.3 has 245 entries |
| **othello** | **0.0%** | 0/14 | Zero — v2.3 has 541 entries |

## Live Leaderboard (Block 7784716)

| Rank | Miner | GAME | NAVWORLD | SWE-SYNTH | LIVEWEB |
|------|-------|------|----------|-----------|---------|
| 1 | wisercat | 45.60 | 23.36 | 45.00 | 18.64 |
| 2 | vera6 | 48.85 | 21.94 | 31.00 | 18.10 |
| 3 | AnastasiaF | 47.74 | 17.87 | 37.37 | 23.21 |
| 4 | AnastasiaF-2 | 38.09 | 19.33 | 44.00 | 16.00 |
| 5 | RLStepone | 45.80 | 18.86 | 41.00 | 13.43 |
| 6 | coffie3 | 37.90 | 21.01 | 47.00 | 15.39 |
| **v2.2** | **ours** | **26.04** | **6.10** | **N/A** | **6.83** |

## v2.3 Expected (APPROVED, awaiting launch)

| Env | v2.2 | v2.3 Change | Expected | Confidence |
|-----|------|-------------|----------|------------|
| GAME | 26.04 | v4: all 7 games, 4657 entries | **35-43** | HIGH |
| LIVEWEB | 6.83 | format fix `_normalize_tool_calls_qwen3()` | **8-15** | MEDIUM |
| NAVWORLD | 6.10 | unchanged data | **5-8** | LOW |
| SWE-SYNTH | N/A | unchanged, must fix Docker | **?** | — |

## v2.4 Draft — NAVWORLD Data Source Overhaul (Pipeline Ahead)

**Variable**: Replace qwen-max NAVWORLD data (2205 entries) with GPT-5.4 distillation
**Hypothesis**: Same-family distillation (Qwen3-max → Qwen3-32B) limits generalization. Cross-family teacher (GPT-5.4) provides diverse reasoning patterns. Expected: NAVWORLD 12-18 (vs 6.10).
**User approved this direction** (2026-03-20).

### Data Status Needed for v2.4
- Remove: 2205 qwen-max NAVWORLD entries
- Keep: 419 Claude Sonnet entries (proven quality)
- Generate: ~1000-1500 GPT-5.4 NAVWORLD entries across all 7 types
- Total target: ~1500-2000 NAVWORLD entries (quality > quantity)

### Rank-Jump ROI (priority order)
1. **NAVWORLD** (6.10 vs #6=21.01, gap=15): HIGHEST. v2.4 primary target.
2. **GAME** (26→35-43 from v2.3): wait for v2.3 results
3. **SWE-Infinite** (replacing SWE-SYNTH): new data-swe role deploying pipeline. Python bottleneck (3.7% smoke test pass rate). Go/Rust tasks much easier.
4. **LIVEWEB** (6.83 vs #6=15.39, gap=8.6): format fix in v2.3 should close gap. Data confirms compression NOT needed (388 entries fit seq=16K). Root cause was format bug.

## Action Items

- [x] v2.2 full eval (GAME 26.04, NAVWORLD 6.10, LIVEWEB 6.83, SWE-SYNTH failed)
- [x] v2.3 approved and data ready
- [x] v2.3 training LAUNCHED (06:32 UTC, 4xH200, ETA ~13:45 UTC)
- [x] data-swe role created and directive sent (SWE-Infinite pipeline)
- [ ] v2.4 NAVWORLD GPT-5.4 data generation (Data working on pipeline)
- [ ] v2.3 eval + results analysis
- [ ] v2.4 draft finalization (after v2.3 eval)
