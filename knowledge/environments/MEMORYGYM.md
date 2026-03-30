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

## Current Synthesis Path

Current public synthesis flow:

1. `forge data memorygym-gen --seeds N --tier-mix -j 4 -o data/memorygym_raw.jsonl`
2. `forge data memorygym-split -i data/memorygym_raw.jsonl -o data/memorygym_split.jsonl --target 20000 --balance`
3. `forge data ingest data/memorygym_split.jsonl --env MEMORYGYM --source <tag>`

Notes:

- **Primary source of truth**: `forge/data/memorygym_gen.py` and `forge/data/memorygym_split.py`
- **Script wrappers**: `scripts/memorygym_hybrid_gen.py` and `scripts/memorygym_split_events.py`
- `memorygym-gen` now uses a lightweight in-memory backend for fast raw trajectory generation
- `memorygym-split` is what produces canonical-ready event samples

## Current Data: 1400 entries (2026-03-22)

Generated via the MemoryGym raw-generator + split pipeline. The current generator uses a lightweight backend to preserve tool-result formatting without ChromaDB embedding overhead.

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

## Data Quality Deep Audit (2026-03-27)

### What works
- `<tool_call>` text format matches eval's `_extract_tool_calls()` parser exactly
- System prompt identical to eval's `SYSTEM_PROMPT`
- Tool result format (`[Write] Stored (id=...)`, `[memory_search] ...`) matches eval
- All 500 hybrid entries have complete Write→Search→Answer chains
- Tool usage per hybrid entry: avg 21 Writes, 30 Searches, 17 Submits — realistic

### Critical problems

**1. Train/eval context mismatch (BLOCKING)**
- Eval uses **redaction** after each event: `del messages[1:]` + memory summary (`stream_agent.py:734`)
- Hybrid training data has **full conversation history** — no redaction between events
- Generator confirms: `"No redaction — model must learn complete chain"` (line 262)
- Result: during eval, model sees `[system] + [memory_summary] + [question]`; during training, model sees 8+ prior assistant turns before the first question
- **The model learns to answer with full ingest context, but eval gives only a summary**

**2. 50% of data skips storage learning**
- 700 qa_only entries start from memory summary → only teach Search+Submit
- 700 hybrid entries teach Write+Edit+Search+Submit
- Storage Breadth is 30% of score — half the data doesn't train this skill

**3. Edit failure rate 34.5%**
- 1032 "Text not found in memory" vs 1963 successful Edits
- Cause: generator's old_text matching is fragile (compact format changes)
- Model learns that Edit often fails → may give up on corrections during eval
- Memory Maintenance is 25% of score

**4. Small dataset, signal dilution**
- 1400 entries = ~6% of a 23K training mix
- Prior experiments: 480 entries → 3/10. Current 1400 is only 3x more, with mismatch issues

**5. No reasoning chains**
- Assistant messages are deterministic: `Search → "From my memory: X. The answer is X." → Submit`
- Eval has 20 comprehension types (synthesis, aggregation, cross_category, etc.)
- Template-generated reasoning doesn't teach real multi-hop/comparison thinking

**6. SFT ceiling confirmed by 4 prior experiments**

| Version | Data | Correct | Key Finding |
|---------|------|---------|-------------|
| SFT v1 | old format | 0/10 | Learned Write only |
| SFT v2b | 480 traj | **3/10** | First correct answers; 8 epochs needed |
| SFT v3 | 480 traj | 0/10 | Learned format but lost reasoning |
| GRPO v3 | RL on SFT v3 | 5/10 | Model cheated: answered from context, not memory |

### Verdict
Current data **cannot reliably teach the model to score**. The context mismatch means even correct tool patterns will break during eval. SFT ceiling is 3-6/10 even with perfect data.

### To make SFT data effective (if pursued)
1. **Simulate redaction in generator**: after each event, wipe context and insert memory summary (match eval exactly)
2. **Fix Edit failures**: ensure old_text matches stored content precisely before generating Edit calls
3. **Remove qa_only_strategic** (200 entries): teaches QA without any prior context, least useful
4. **Add thinking chains**: use strong teacher model for reasoning questions
5. **Scale to 3000+**: needed to register signal in mixed training

### Key Findings (unchanged)
1. **SFT ceiling ~4-6/10** — teaches tool format but not the causal chain
2. **GRPO is critical path** — MemoryEnv RL environment ready, reward aligned with eval scoring
3. **GPT-5.4 distillation failed** — multi-step tool use too weak (1-2/10 correct)
4. **Anti-cheating works** — 9 simulation strategies verify genuine capability

## Data Pipeline
- Raw generator: `forge data memorygym-gen`
- Event splitter: `forge data memorygym-split`
- Canonical ingest: `forge data ingest --env MEMORYGYM`
- Canonical: `data/canonical/memorygym.jsonl`
- RL env: `MemoryEnv` class with binary/shaped rewards, compatible with verl/slime adapters
