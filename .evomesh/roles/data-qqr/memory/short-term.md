# Short-term Memory
## 2026-03-21 Loop 100 — V5 Canonical Merged

### Done
- **V5 canonical merged**: 1420 entries, replacing old 951 (all had format bugs)
- **HF synced**: monokoco/affine-sft-data/navworld.jsonl
- **Quality audited**: 99.8% pass, fabrication entries filtered
- **4 critical fixes**: transport format, Chinese prompts/schema, scorer keyword alignment, D1/D2 label fix
- **Type distribution**: single_poi 273, intercity 265, family_study 258, multiday 169, food_tour 151, hybrid 154, business 154

### In-progress
- 8 gen processes still running (API 504s slowing)
- Incremental merges each loop

### Awaiting
- Next training run with V5 data
- Strategist to schedule experiment with V5 NAVWORLD
