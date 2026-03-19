# Gap Analysis

**Last updated**: 2026-03-19 (Strategist loop 46)
**Status**: Machine ONLINE. v2 training likely complete (GPUs at 0%). Trainer directed to check + eval.

## Live Leaderboard (Block 7776573)

| Rank | Miner | GAME | NAVWORLD | SWE-SYNTH | LIVEWEB | LGC-v2 | PRINT | Weight |
|------|-------|------|----------|-----------|---------|--------|-------|--------|
| 1 | affshoot | 49.44 | 16.28 | 43.00 | 19.16 | 89.11 | 79.80 | 0.508 |
| 2 | vera6 | 50.56 | 22.52 | 30.00 | 19.44 | 90.40 | 82.56 | 0.254 |
| 3 | RLStepone | 48.73 | 20.34 | 38.00 | 15.93 | 87.60 | 80.81 | 0.127 |
| 4 | AnastasiaFantasy | 40.78 | 22.16 | 37.00 | 17.16 | 83.20 | 80.83 | 0.063 |
| 5 | EdmondMillion-19 | 45.55 | 20.69 | 38.00 | 14.57 | 86.80 | 81.73 | 0.032 |
| 6 | coffie3 | 40.26 | 20.72 | 42.00 | 16.86 | 83.61 | 74.19 | 0.016 |

**Changes from Block 7776423**: wisercat DROPPED OFF (was #1!). affshoot back to #1. coffie3 new at #6.
**Leaderboard is volatile** — rankings shift significantly between blocks. Balance is key.

**Notable**: EdmondMillion UID 68 (weight=0) has: GAME 47.05, NAVWORLD 24.27, SWE-SYNTH 42.00 — would be #1 if not Pareto-filtered.

## 4-env GM Analysis (our focus environments)

**Competitor 4-env GMs (GAME × NAVWORLD × SWE-SYNTH × LIVEWEB)**:
- affshoot #1: (49.44 × 16.28 × 43.00 × 19.16)^(1/4) ≈ 28.5
- vera6 #2: (50.56 × 22.52 × 30.00 × 19.44)^(1/4) ≈ 28.9
- RLStepone #3: (48.73 × 20.34 × 38.00 × 15.93)^(1/4) ≈ 28.4

**4-env field is tight** — top 3 all cluster around 28-29. NAVWORLD is the differentiator (affshoot weakest at 16.28).

**Note**: LGC-v2/PRINT 不训练（用户指令）。接受这些环境的零分影响。

## Gap Table (vs #1 affshoot)

| Env | #1 Score | Field Range | Our v2 Data | Expected Score | Gap to #1 | Priority |
|-----|----------|-------------|-------------|----------------|-----------|----------|
| GAME | 49.44 | 40.3-50.6 | 2641 entries | 25-35 | -14 to -24 | P1 |
| NAVWORLD | 16.28 | 16.3-24.3 | 2248 entries | 5-8 | -8 to -11 | **P0** |
| SWE-SYNTH | 43.00 | 30.0-43.0 | 983 entries | 10-25 | -18 to -33 | P1 |
| LIVEWEB | 19.16 | 14.6-19.4 | 18 entries | 15-20 | -4 to +1 | Maintain |
| LGC-v2 | 89.11 | 83.2-90.4 | **不训练** | 0 | N/A | 禁止 |
| PRINT | 79.80 | 74.2-82.6 | **不训练** | 0 | N/A | 禁止 |

## LGC-v2/PRINT: 禁止训练（用户指令）

用户明确指示：所有阶段只训练 4 环境。LGC-v2/PRINT 不训练，接受零分影响。

## v3 Data Plan (4-env)

| Env | Count | Source |
|-----|-------|--------|
| GAME | 2641 + 183 (D7 HIGH gin_rummy) | canonical + v3 staging |
| NAVWORLD | 2248 + 400 (D6 Phase 1) | canonical + new diverse data |
| SWE-SYNTH | 983 | canonical |
| LIVEWEB | 18 | canonical |
| **Total** | **~6473** | 4-env only |

## ROI Analysis (updated for Block 7776423)

| Action | Impact | Effort | ROI |
|--------|--------|--------|-----|
| NAVWORLD D6 Phase 1 diversity (+400) | Break 5-template ceiling | Medium | **Highest** |
| GAME D7 gin_rummy merge (+183 HIGH) | Better gin_rummy learning | Low | High |
| Resolve machine access | Unblock all work | User action needed | **BLOCKER** |

## Action Items

- [x] D1-D7 complete
- [x] ~~Machine unreachable~~ → RESOLVED
- [ ] 🔴 **D10**: canonical 数据 schema 一致性修复（阻塞训练）
- [ ] **D6 Phase 1**: execute NAVWORLD diversity expansion (400 new entries)
- [ ] **D7 merge**: 183 HIGH gin_rummy entries → canonical
- [ ] v2 eval results → diagnose per-env performance
- [ ] v3 experiment YAML design (pending v2 results)
