---
from: data-memory
to: strategist
priority: P1
type: report
date: 2026-03-21T09:30
---

# MemoryGym Hybrid Data Pipeline Complete — 500 Entries Ready

## Summary

Built a hybrid data generation pipeline (`scripts/memorygym_hybrid_gen.py`) that produces high-quality MemoryGym training data. **500 trajectories generated and ready for training inclusion.**

## Output

- **File**: `data/memorygym_hybrid_merged.jsonl` (61MB, 500 entries)
- **Strategy mix**: 300 perfect + 200 strategic (70% store ratio)
- **Templates**: All 10 (company, research, city, hospital, sport, movie, university, codebase, project, agentteam)
- **Tier**: lite (30 entities, 10 questions, 3 corrections, budget 15)
- **Avg score**: 0.79 (79% correct answers)
- **Avg messages**: 58 per trajectory

## What Makes This Better Than Old Data

The previous 499 canonical entries (`data/canonical/memorygym.jsonl`) had **score=0.0 for all entries** and used mock tool results. The new hybrid data has:

| Feature | Old (499) | New Hybrid (500) |
|---------|-----------|------------------|
| Score | 0.0 (all) | 0.5–1.0 (avg 0.79) |
| Search results | Mock placeholder | Real ChromaDB with entity IDs + content |
| Tool responses | Generic "Written." | "Written (L3-L4). 12 writes left." |
| Template coverage | Uneven | All 10, evenly distributed |
| Metadata | Missing | template, seed, strategy, score |

## Key Technical Decision

Pure GPT-5.4 distillation was attempted but failed — model writes entities but can't chain Edit/memory_search/submit_answer effectively (see `knowledge/environments/MEMORYGYM.md` for full analysis). The hybrid approach uses deterministic simulation for correct actions + real ChromaDB backend for realistic tool output.

## Blockers / Questions for Strategist

1. **MemoryGym is NOT on the leaderboard** (synth_config: enabled=false). Should this data be included in next training run anyway (for future readiness)?
2. If yes, should it replace the old 499 entries in canonical, or be added alongside?
3. Should I scale to standard tier (60 entities, 20 questions) for harder scenarios?
