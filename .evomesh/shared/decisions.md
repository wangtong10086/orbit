# Shared Decisions — affine-swarm

Append-only log of cross-role decisions.

---

## 2026-03-18: Architecture decisions

1. **Three-role architecture**: Strategist (WHAT+WHY) → Trainer (HOW to train) + Data (HOW to get data). Separating strategy from execution to prevent tunnel vision.
2. **One variable per experiment**: Each experiment changes exactly one thing. Multi-variable changes split into sequential experiments.
3. **Data mix is shared decision**: Strategist proposes, Data validates. Neither can unilaterally set the mix.
4. **Forced adversarial review**: Training cannot launch without adversarial exchange between roles.
5. **NAVWORLD v9 replaces v8**: v8 NAVWORLD data invalid (AMAP key expired). v9 (742+ entries, 100% real POI) is authoritative.
6. **Distillation model: DashScope qwen3-max only**: DeepSeek and other third-party models forbidden. Exception: GAME uses programmatic bots.
7. **canonical/ is single source of truth**: One env = one file. Schema: `{"messages":[...], "env":"...", "score": float}`.
8. **Focus on 4 environments**: GAME, NAVWORLD, SWE-SYNTH, LIVEWEB. LGC-v2 and PRINT excluded from training and data investment.
9. **Think in ranks, not scores**: decay_factor=0.5, rank improvements matter more than raw score.
10. **SFT plateau trigger**: 2x data yields <15% improvement → escalate to DPO.
