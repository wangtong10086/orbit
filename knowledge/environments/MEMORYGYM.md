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
Maintenance score is gated by storage coverage: if stored_count/n_entities < 0.5, maintenance is scaled down. Must store at least 50% of entities for full maintenance credit.

### Answer Validation (4-layer)
exact → numeric (int-exact, float 2% tolerance) → synthesis ("EntityName (value)") → abstention.

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
- Has RL environment ready for GRPO training

## Current Data: 1400 entries (2026-03-22)

Generated via `scripts/memorygym_hybrid_gen.py` — deterministic actions + real ChromaDB backend.

| Metric | Value |
|--------|-------|
| Total entries | 1400 (700 full pipeline + 700 QA-only) |
| Score | avg=0.78, range=[0.50, 1.00], all >0 |
| Tiers | 1000 lite + 200 standard + 200 hard |
| Templates | all 10, evenly covered |
| Strategies | 600 perfect + 400 strategic + 200 hard-perfect |
| Tool results | Real ChromaDB UUIDs + content |
| Anti-cheating | 9 strategies × 10 templates ALL PASS |
| Format alignment | System prompt, `<tool_call>`, answer formats match eval exactly |
| Intermediate files | Removed. Only `data/canonical/memorygym.jsonl` remains |

### Quality Audit (2026-03-22)
- 4-axis coverage: Write 100%, Edit 100%, Search→Answer 100%, Abstention 100%
- Reasoning chains: 3590 total (grounded 1700, correction 946, counting 940)
- Question distribution: retrieval 30%, counting 29%, aggregation 8%, extremes 7%
- Hard tier avg score 0.69 (4:1 entity-to-budget pressure)

## Key Findings

1. **SFT ceiling ~4-6/10** — teaches tool format but not the causal Write→Search→Answer chain
2. **GRPO is critical** — MemoryEnv RL environment ready, reward aligned with eval scoring
3. **GPT-5.4 distillation failed** — multi-step tool use too weak (1-2/10 correct). Hybrid approach (deterministic actions + real ChromaDB) was the solution
4. **Anti-cheating works** — 9 simulation strategies verify genuine capability (perfect=100%, guesser=0%, smart_guesser≤5%)

## Prior Training Experiments

| Version | Data | Correct | Key Finding |
|---------|------|---------|-------------|
| SFT v1 | old format | 0/10 | Learned Write only |
| SFT v2b | 480 traj | **3/10** | First correct answers; 8 epochs needed |
| SFT v3 | 480 traj | 0/10 | Learned format but lost reasoning |
| GRPO v3 | RL on SFT v3 | 5/10 | Model cheated: answered from context, not memory |

## Data Pipeline
- Generator: `scripts/memorygym_hybrid_gen.py`
- Canonical: `data/canonical/memorygym.jsonl`
- RL env: `MemoryEnv` class with binary/shaped rewards, compatible with verl/slime adapters
