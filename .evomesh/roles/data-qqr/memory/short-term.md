# Short-term Memory
## 2026-03-22 Loop 1 — Status Check

### Current State
- **Canonical**: 1471 entries (was 1426, +45 incremental since last session)
- **All 1471 pass audit** — 100% valid
- **v2.10**: TRAINING (~15% done) — first test of V5 format-fixed data
- **Generation BLOCKED**: GPT-5.4 proxy returning 504 errors. Claude proxy also 504.
- **No inbox directives** from Strategist

### Type Distribution (canonical)
- family_study: 277, single_poi: 273, intercity: 265
- multiday: 188, hybrid: 160, food_tour: 155, business: 153
- **Weakest types**: business (153), food_tour (155), hybrid (160) — target these when API recovers

### Awaiting
- v2.10 eval results — first test of V5 format-fixed data
- API proxy recovery — both GPT-5.4 and Claude endpoints returning 504
- If NAVWORLD score improves significantly → V5 approach validated
- If not → investigate further (scorer debug, data diversity, etc.)

### Next Actions (when unblocked)
1. Generate ~30 more business + food_tour + hybrid entries to balance distribution
2. Analyze v2.10 eval results per-type when available
3. If APIs stay down, investigate alternative generation approaches
