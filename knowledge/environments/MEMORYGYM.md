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
- **1400 canonical entries** (2026-03-22 hybrid gen v2): all score>0, real ChromaDB results, 3 tiers
- Has RL environment ready for GRPO training

## Critical Data Quality Analysis (2026-03-21)

### Old 499 entries: REPLACED (2026-03-22)
Previous entries had score=0.0, mock search results. Now replaced with 1200 hybrid entries.

### Current 1400 entries: Production-ready (2026-03-22)
Generated via `scripts/memorygym_hybrid_gen.py` — deterministic actions + real ChromaDB backend.
- **700 full pipeline** (Write+Edit+Search+Answer complete chain) + **700 QA-only** (Search+Answer eval conditions)
- **Score**: avg=0.78, range=[0.50, 1.00], all >0 (no filtering risk)
- **Tiers**: 1000 lite (30 entities) + 200 standard (60 entities) + 200 hard (120 entities)
- **Templates**: all 10 evenly covered
- **Strategies**: 600 perfect + 400 strategic + 200 hard-perfect
- Hard tier teaches extreme selectivity (4:1 entity-to-budget ratio, avg score 0.69)

### Resolved Gaps (hybrid v2)

| Gap | Old (499) | New (1200) | Status |
|-----|-----------|------------|--------|
| **Tool results** | Mock ("Results for X...") | Real ChromaDB UUIDs + content | ✅ Fixed |
| **Score field** | 0.0 (placeholder) | 0.50-1.00 (real) | ✅ Fixed |
| **Write results** | "Written. Budget remaining." | "Stored (id=uuid). N writes left." | ✅ Fixed |
| **Edit results** | "Edited. Budget remaining." | "Edited. N writes left." | ✅ Fixed |
| **Template coverage** | Unknown (299 missing meta) | All 10 even | ✅ Fixed |
| **Reasoning chains** | None | Grounded in search results | ✅ Fixed |

### Remaining Gaps
| **Diversity** | 2 deterministic strategies only | Real models make varied decisions | Narrow behavioral range |
| **Score field** | 0.0 (placeholder) | Training pipeline may FILTER score=0 as failures | Data may be silently excluded |

### Prior Training Experiments (from devlog)

| Version | Data | Correct | Key Finding |
|---------|------|---------|-------------|
| SFT v1 | old format | 0/10 | Learned Write only |
| SFT v2b | 480 traj (strategic+perfect) | **3/10** | First correct answers; 8 epochs needed |
| SFT v3 | 480 traj (Write/Edit/Read) | 0/10 | Learned Write format but lost reasoning (loss too low) |
| GRPO v3 | RL on SFT v3 | 5/10 | Model cheated: answered from context, not memory |

**Key lesson**: SFT alone teaches tool format but NOT the complete Write→Search→Answer chain. GRPO helps but model exploits context window instead of using memory.

### What Real Distillation Needs
1. Run `bench.py --model <strong_model>` (e.g., GPT-5.4 via Chutes)
2. Collect full trajectories with **real** tool results from ChromaDB backend
3. Filter for score>0 (only successful episodes)
4. Include real memory_search results with actual content
5. Each trajectory includes the selective redaction pattern (context reset + memory summary)

### Distillation Architecture
```
bench.py --model gpt-5.4 --tier standard --template X --seed N
  → stream_agent.py drives real LLM interaction
  → ChromaDB backend provides real search results
  → trajectory saved to eval/model_template_sN.json + trajectory.json
  → trajectory_to_conversation() converts to messages format
```

## GPT-5.4 Distillation Pilot (2026-03-21)

### Setup
- Model: gpt-5.4 via OpenAI-compatible endpoint (OPENAI_BASE_URL in .env)
- Chutes TEE models return 403 (access issue) — use OpenAI endpoint instead
- Default system prompt: GPT-5.4 returns EMPTY during ingest (no tool calls)
- Enhanced prompt (scripts/memorygym_distill.py): forces `<tool_call>` format

### Results (company, seed=0, lite tier)
- **13 writes, 14 stored** (vs 0 writes with default prompt)
- **2/10 correct** (both abstention — correctly said "I don't have enough")
- Corrections: searched but used submit_answer instead of Edit (0/3 applied)
- Questions: mostly "I don't have enough information" without searching
- Judge infrastructure: Kimi-K2.5-TEE on Chutes timing out (300s)

### Failure Analysis
1. First ingest batch: still 0 writes (model warming up)
2. Corrections: model describes intent ("Updated...") but doesn't call Edit tool
3. Questions: model doesn't use memory_search before answering (5/8 questions)
4. When it does search, data is there but answer extraction is wrong

### Loop 4: Few-shot prompt + Qwen3-235B-Thinking
- Added few-shot examples (Write/Edit/memory_search patterns) to distill prompt
- GPT-5.4 seed=1: 11 writes, 12 stored, but **still 1/10 correct**
- Model now does memory_search (7/10 questions) but **doesn't extract answers from results**
- Sees "Stratos Systems | Revenue: $31,479.3M" but answers "I don't have enough"
- For synthesis questions needing 5 entities, single search is insufficient
- Qwen3-235B-Thinking: also 403 on Chutes. ALL Chutes models blocked.
- Judge infra: Kimi-K2.5-TEE times out (300s) — all non-abstention judged as "failed"

### Root Cause: GPT-5.4 multi-step tool use weakness
1. ✅ Write: works with enhanced prompt
2. ❌ Edit: doesn't call Edit during corrections
3. ⚠️ memory_search: searches but gives up after 1 result (needs multiple searches)
4. ❌ Answer extraction: sees data in results but defaults to abstaining

### Hybrid Approach: IMPLEMENTED (Loop 5)
**`scripts/memorygym_hybrid_gen.py`** — deterministic actions + real ChromaDB results.

**v1 batch (100 trajectories)**:
- 10 templates × 10 seeds, lite tier (30 entities, 10 questions, 15 budget)
- Avg 59 messages, avg 79% correct (rest are valid abstentions)
- Real ChromaDB search results with entity IDs + full content
- Real execute_tool() responses (Write/Edit/memory_search/submit_answer)
- Score=0.79 avg (vs score=0.0 for old 499 entries)
- Output: `data/memorygym_hybrid_v1.jsonl` (13MB, 100 entries)

**Key improvements over old 499 entries**:

| Feature | Old (499) | Hybrid v1 (100) |
|---------|-----------|-----------------|
| Score field | 0.0 (placeholder) | 0.5-1.0 (real) |
| Tool results | Mock ("Results for X...") | Real ChromaDB IDs + content |
| Write results | "Written. Budget remaining." | "Written (L3-L4). 12 writes left." |
| Edit results | "Edited. Budget remaining." | "Edited. 4 writes left." |
| Search results | "Results for X..." | "[uuid] Entity \| attr: val \| ..." |
| Template coverage | Uneven (299 unknown) | All 10 even (10 each) |
| Metadata | Missing | template, seed, strategy, score |

**v1 merged (500 trajectories, Loop 6)**:
- `data/memorygym_hybrid_merged.jsonl` — 500 entries, 61MB
- 300 perfect (seeds 0-29) + 200 strategic (seeds 0-19), all 10 templates
- Avg 58 msgs, avg 79% correct
- Ready for training inclusion (pending strategist approval + MemoryGym on leaderboard)

## Key Findings
- Anti-cheating: 9 simulation strategies verify scores (perfect=100%, guesser=0%, smart_guesser≤5%)
- Deterministic SFT data teaches format but not capability
- Real distillation via bench.py is the correct path for quality data
- **GPT-5.4 needs enhanced prompt + few-shot to follow MemoryGym protocol**
- GRPO with MemoryEnv is the long-term training approach (reward aligned with eval)
