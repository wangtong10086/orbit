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

## Current Data: v4g — 20000 balanced per-event samples

**Pipeline**: `memorygym_hybrid_gen.py --tier-mix` → `memorygym_split_events.py --balance --target 20000`

| Metric | Value |
|--------|-------|
| Total entries | **20,000** |
| Median tokens | ~1,600 (max ~10K) |
| Token limit | **0% > 32K** |
| Distribution | ingest 30% / correction 20% / question 45% / noise 5% |
| Tier mix | lite 30% / standard 50% (eval tier) / hard 20% |
| Format | `<tool_call>` XML in content, strict user/assistant alternation |
| HF | synced (`monokoco/affine-sft-data/memorygym.jsonl`) |

### v2.28 Eval Results
| Checkpoint | MG Score | Notes |
|------------|----------|-------|
| ckpt600 | **51.5%** | 27/50 seeds |
| ckpt800 | 75.0% | 1 seed only (noise) |
| ckpt1200 | **46.2%** | 100 scores |
| Perfect strategy | 57.5% | theoretical ceiling |

## Pipeline
- Generator: `scripts/memorygym_hybrid_gen.py --tier-mix --seeds 100 -j 4`
- Splitter: `scripts/memorygym_split_events.py --balance --target 20000`
- Canonical: `data/canonical/memorygym.jsonl`
- Regenerate time: <2 min locally

## Next Steps
- GRPO (MemoryEnv ready) to break 57.5% SFT ceiling
- Per-axis analysis from eval results to target weak axes
