# MemoryGym Environment

## Overview
Memory management evaluation: model receives a stream of entity documents under a write budget, must selectively store, update on corrections, and answer questions. Deterministic (same seed = same scenario). Cheat-proof via 9 simulation strategies.

## Source
- Repo: `repos/MemoryGym/`
- Eval entry: `memorygym/env.py` → `Actor.evaluate()`
- Bench CLI: `python -m memorygym.bench`

## Scoring (4-axis weighted composite)

| Axis | Weight | Metric |
|------|--------|--------|
| Storage Breadth | 30% | retrieval question accuracy (did you store entity?) |
| Memory Maintenance | 25% | update question accuracy × min(coverage/0.5, 1.0) |
| Reasoning | 25% | 20 comprehension types (synthesis, aggregation, cross_category, etc.) |
| Efficiency | 20% | correct_answers / write_budget, capped at 1.0 |

Composite = weighted sum of 4 axes.

### Key detail: Maintenance gating
Maintenance score is gated by storage coverage: if stored_count/n_entities < 0.5, maintenance is scaled down. This means you MUST store at least 50% of entities to get full maintenance credit.

## Tiers

| Tier | Entities | Questions | Corrections | Write Budget |
|------|----------|-----------|-------------|-------------|
| lite | 30 | 10 | 3 | 15 |
| standard | 60 | 20 | 5 | 30 |
| hard | 120 | 40 | 10 | 30 |
| multi | 60 | 20 | 5 | 30 (3 sessions) |

Budget pressure: entities > budget in all tiers (selective storage required).

## World Templates (10)
company, research, city, hospital, sport, movie, university, codebase, project, agentteam

Each template generates entities with typed attributes (6 dtypes), relationships, corrections, contradictions, and 20+ reasoning question types.

## Data Pipeline
- `memorygym/training/env.py` → `generate_sft_trajectory()`: deterministic SFT data from simulation
- `scripts/generate_sft_data.py`: CLI wrapper, outputs JSONL `{"messages": [...]}` format
- Strategies: "perfect" (rank by importance, top budget) or "strategic" (70% random)
- Existing canonical: 499 entries in `data/canonical/memorygym.jsonl` (standard tier, ~103 msgs each)
- RL env: `MemoryEnv` class with binary/shaped rewards, compatible with verl/slime adapters

## Memory Interface (tools the model uses)
- `Write(content)` — store to memory (costs 1 budget)
- `Edit(old_text, new_text)` — update memory (free during corrections)
- `Read()` — read all memory
- `memory_search(query)` — search memory (top-k results)
- `submit_answer(answer)` — answer a question

## Event Stream (what the model sees)
1. DOCUMENTS — batch of entity docs → store selectively
2. CORRECTION — entity data changed → search + edit memory
3. NOISE — supplementary info → usually skip
4. SESSION_BREAK — context reset, memory preserved → use memory_search
5. QUESTION — answer from memory → search + submit_answer

## Status
- **Not on leaderboard** currently
- synth_config: enabled=false, priority=99
- 499 canonical entries exist but unused in training
- Has RL environment ready for GRPO training

## Key Findings
- Anti-cheating: 9 simulation strategies verify scores (perfect=100%, guesser=0%, smart_guesser≤5%)
- Training data can be generated deterministically (no API calls needed)
- Quality depends on strategy diversity and template coverage
