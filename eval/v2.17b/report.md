# v2.17b 实验报告 (with SWE-I)

> Status: Archived evaluation report
> Authority: Non-normative
> Last reviewed: 2026-04-04
> Use this file as a historical result record, not as a current specification.


## 实验概述
- **变量**: 包含 SWE-Infinite 374 条数据（vs v2.17a 不含）
- **数据**: GAME 5584 + NW 1658 + LW 1159 + SWE-I 374 = 8775
- **训练**: lr=5e-5, epochs=1, 258 steps, 4×H200 DDP

## 评测结果

| Env | v2.17b | v2.16 | v2.13b | 竞争者 (affshoot) |
|-----|--------|-------|--------|-------------------|
| GAME | **29.72** | 26.75 | 28.12 | 47.44 |
| NAVWORLD | **35.48** | 35.46 | 25.13 | 24.14 |
| LIVEWEB | 4.17 | 6.49 | 11.03 | 20.40 |

## GAME Per-Game Breakdown

| Game | N | Non-zero | Mean | Max | vs v2.16 |
|------|---|----------|------|-----|----------|
| goofspiel | 15 | 87% | 86.7 | 1.00 | 同 |
| leduc_poker | 14 | 100% | 52.5 | 0.77 | +1.7 |
| gin_rummy | 14 | 100% | 45.6 | 0.72 | -1.8 |
| **liars_dice** | 15 | **20%** | **20.0** | **1.00** | **+20.0 突破！** |
| hex | 14 | 0% | 0.0 | 0.00 | 同 |
| othello | 14 | 0% | 0.0 | 0.00 | 同 |
| clobber | 14 | 0% | 0.0 | 0.00 | 同 |

**liars_dice 首次得分**（3/15, max 1.00）。SWE-I 的编程推理可能帮助了概率/bluffing 推理。

## A/B 对比 (v2.17a vs v2.17b)

| Env | v2.17a (no SWE-I) | v2.17b (with SWE-I) | SWE-I 影响 |
|-----|-------------------|---------------------|-----------|
| GAME | ~30 (running) | 29.72 | ~neutral |
| NW | ~41 (running) | 35.48 | -5.5 (略负) |
| LW | ~6.5 (running) | 4.17 | -2.3 (负面) |
| liars_dice | 0% (v2.16 ref) | 20% | SWE-I 帮助 |

## LIVEWEB 低分根因
与 v2.16 相同：GAME v12 think-then-act 模式导致浏览器导航循环。LW 0 errors（cache 正常），问题纯粹是模型行为。

## 结论
- SWE-I 对 liars_dice 有显著帮助（0→20%），对 NW/LW 略有负面
- v2.17b 综合不如 v2.17a（NW -5.5, LW -2.3, liars_dice +20）
- 最终结论需等 v2.17a 完成后 A/B 对比
