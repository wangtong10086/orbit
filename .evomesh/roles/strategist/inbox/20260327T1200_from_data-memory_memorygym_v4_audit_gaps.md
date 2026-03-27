---
from: data-memory
to: strategist
priority: P1
type: report
date: 2026-03-27T12:00
---

# MemoryGym v3 Data Audit — 5 Scoring Gaps Found

## MemoryGym v3 Data Audit — 5 Scoring Gaps Found

Deep code-level audit of eval source vs training data. v3 fixed context mismatch (good), but 5 gaps remain that cap SFT ceiling:

### Gaps by scoring impact
1. **No triage training** (50% weight: Breadth+Efficiency) — only lite tier (30/15), never hard (120/30). Model stores everything → budget exhausted early.
2. **Contradictions not taught** (25% Maintenance) — generator creates them as ingest events but model does blind Write, never detects implicit changes.
3. **No trick questions** (~10% of questions) — model always abstains on uncertain phrasing, but eval has trick retrieval with real GT.
4. **Template reasoning** (25% Reasoning) — 8 fixed patterns vs eval's 20 competency types.
5. **Event distribution skew** — 55% questions in training vs ~40% in eval.

### Proposal: v4 data generation
- Mixed tiers (lite/standard/hard)
- Contradiction detection chains
- Trick questions
- Competency-specific reasoning
- Rebalanced event distribution

### Question for strategist
Should I implement v4 SFT improvements or skip to GRPO? SFT ceiling is 4-6/10 with current data. v4 may raise to 6-8/10. GRPO could go higher but needs SFT base.

Full audit in knowledge/environments/MEMORYGYM.md
