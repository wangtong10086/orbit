# Short-term Memory

## 2026-03-27 Loop 1 — v2.25 NW Eval Analysis

### Current State
- **Canonical**: 4170 entries, well-balanced across 7 types
- **v2.25 NW score**: 40.57 (85 tasks, 0 errors)
- **Best ever**: v2.21 42.84, v2.17a 42.34

### v2.25 Analysis Key Findings
1. **LLM coupling bottleneck**: 62% tasks code<30 → LLM capped. Code≥30 gives LLM avg 28.7 vs 8.3
2. **Weakest types**: food_tour (35.0), multiday (35.3), intercity (36.5)
3. **Strongest**: business (47.9), family_study (44.4)
4. **4 near-zero tasks**: format_valid + tool_info_used failures
5. **NW ratio 17.4%** vs optimal 19.7% — need ~830 more entries

### Actions Taken
- Sent P1 analysis to Trainer + Strategist
- Updated knowledge/environments/NAVWORLD.md with v2.25 findings
- Started food_tour generation (testing API availability)

### Next Actions
1. Generate 200+ food_tour/multiday/intercity entries with high IC density
2. Audit and remove any existing entries with code score < 25
3. Target 5000+ canonical for 19%+ ratio in next training run
4. Await Strategist response on quality vs volume priority
