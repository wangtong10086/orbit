# Gap Analysis

**Last updated**: 2026-03-20 16:00 UTC

## Training History

| Ver | GAME | NAVWORLD | LIVEWEB | Loss | seq | Data | Key Change |
|-----|------|----------|---------|------|-----|------|-----------|
| v2.1 | 25.74 | **8.47** | — | 0.156 | 8192 | 6894 | Baseline |
| v2.2 | 26.04 | 6.10 | 6.83 | 0.224 | 16384 | 7239 | DDP, seq↑ |
| v2.3 | 22.69 | 1.52 | 8.62 | 0.172 | 16384 | 7626 | qwen-max GAME regression |
| v2.4a | pending | pending | pending | 0.231 | 8192 | 5120 | A/B: seq=8192 (eval failed on M2) |
| **v2.4b** | **25.44** | **4.58** | **15.77** | ~0.17 | 16384 | 5278 | **qwen-max removed, GPT-5.4 added** |
| v2.5 | — | — | — | — | 16384 | 5475 | APPROVED: +194 NW GPT-5.4 |

## v2.4b Results — Key Breakthrough

| Env | v2.4b | vs v2.3 | vs #6 | Gap |
|-----|-------|---------|-------|-----|
| GAME | 25.44 | +2.75 ✅ | 37.90 | -12.5 |
| NAVWORLD | 4.58 | +3.06 ✅ (3x) | 21.01 | -16.4 |
| **LIVEWEB** | **15.77** | **+7.15** ✅ | **15.39** | **+0.38 超越#6!** |

### Confirmed Findings
1. **qwen-max removal = NAVWORLD fix** — 1.52→4.58 (3x). NOT seq_len (v2.4b used 16384 and still recovered)
2. **LIVEWEB 15.77 best ever** — competitive with top miners (13-19 range). Already beats #6.
3. **GAME recovered** to v2.1 level. GPT-5.4 distillation: leduc 50.8↑, goofspiel 80.8↑
4. **Zero-tier games still 0%** — liars_dice 250 GPT-5.4 entries had zero effect. Confirmed eval parsing issue.
5. **seq=16384 is fine** — NOT the regression cause. Can keep using it.

## Live Leaderboard (Block 7784716)

| Rank | Miner | GAME | NAVWORLD | SWE | LIVEWEB |
|------|-------|------|----------|-----|---------|
| 1 | wisercat | 45.60 | 23.36 | 45.00 | 18.64 |
| 2 | vera6 | 48.85 | 21.94 | 31.00 | 18.10 |
| 3 | AnastasiaF | 47.74 | 17.87 | 37.37 | 23.21 |
| 6 | coffie3 | 37.90 | 21.01 | 47.00 | 15.39 |
| **v2.4b** | **ours** | **25.44** | **4.58** | **—** | **15.77** ✅ |

## Rank-Jump ROI (priority order)

1. **NAVWORLD** (4.58 vs #6=21.01, gap=16.4): More GPT-5.4 data. v2.5 has 1157 (+194). Trajectory: 8.47→6.10→1.52→**4.58**→?
2. **GAME** (25.44 vs #6=37.90, gap=12.5): Zero-tier = eval parsing. SFT can't fix. Need GRPO or eval-side.
3. **SWE-Infinite** (— vs #6=47): 22 trajectories ready (Go 21, Ruby 1). Pipeline ceiling at 22 until Docker rerun.
4. **LIVEWEB** (15.77 vs #6=15.39): **Already competitive!** More data for margin.

## v2.5 Plan (APPROVED, M2 training)

| Env | v2.4b | v2.5 | Change |
|-----|-------|------|--------|
| GAME | 3918 | 3918 | — |
| NAVWORLD | 963 | **1157** | +194 GPT-5.4 |
| LIVEWEB | 397 | **400** | +3 |
| **Total** | 5278 | **5475** | +197 |

Config: seq=16384, DDP. Expected: NAVWORLD 6-8.

## Dual Machine Assignment
- **M1**: v2.4a eval补测 (model on HF) + liveweb_v8 data gen
- **M2**: v2.5 training → eval

## Action Items
- [ ] v2.4a eval补测 (M1)
- [ ] v2.5 training + eval (M2)
- [x] v2.4b complete — LIVEWEB 15.77 breakthrough
- [x] data-swe: 22 SWE-Infinite trajectories (ceiling until pipeline rerun)
- [ ] NAVWORLD GPT-5.4 continuous generation (data-qqr)
- [ ] GAME zero-tier: eval parsing fix or GRPO (Phase 3)
