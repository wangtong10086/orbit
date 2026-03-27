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

## Current Data: v3 — 5000 per-event samples (2026-03-27)

**Pipeline**: `memorygym_hybrid_gen.py` → 1500 trajectories → `memorygym_split_events.py` → 40K events → downsample to 5000.

Each sample = one event, matching eval's per-event context exactly:
`[system_prompt] + [memory_summary + "OK."] + [event_prompt + tool_calls + results]`

| Metric | Value |
|--------|-------|
| Total entries | 5000 (downsampled from 40K events / 1500 trajectories) |
| Median tokens | **1,823** (max 15,970) |
| Truncation at seq=32K | **0%** |
| Event types | question 55% / ingest 20% / correction 18% / noise 7% |
| Edit success | **99.6%** — fuzzy numeric + attr-name field lookup |
| Reasoning chains | grounded in search results + correction context |
| Context | Matches eval redaction exactly (system + summary + event) |
| HF synced | Yes — `monokoco/affine-sft-data/memorygym.jsonl` |

### v3 design: per-event split matches eval
- Eval does `del messages[1:]` after each event → model sees system + summary + event
- Training data is split at the same boundaries → identical context structure
- Model learns: given summary of stored entities + event → correct tool usage

### v2→v3 change
- v2: full trajectories (median 41K tokens, 87% truncated at 32K) — model never sees questions
- v3: per-event samples (median 1.8K tokens, 0% truncated) — every event fully trained

## Data Quality Deep Audit v2 (2026-03-27, code-level)

### What v3 fixed (working)
- `<tool_call>` XML format matches eval's `_extract_tool_calls()` 3-format parser (XML > markdown > bare JSON)
- System prompt identical to eval's `SYSTEM_PROMPT` (`stream_agent.py:38-75`)
- Redaction between events: `del messages[1:]` + memory summary — matches eval exactly
- Per-event split: each sample = [system + summary + event], 0% truncation
- Edit success 99.6% via fuzzy numeric + attr-name field lookup

### 5 remaining gaps (by scoring impact)

**1. Only `lite` tier trained → no triage learned (Breadth 30% + Efficiency 20% = 50%)**
- Generator default: `--tier lite` (30 entities / 15 budget = 50% compression)
- Eval tiers: standard (60/30 = 50%), **hard (120/30 = 25% — only top 30 out of 120)**
- "perfect" strategy (`hybrid_gen.py:197-203`) stores top-N by importance but model sees no reasoning about WHY to skip
- Model learns: "store everything I see" → runs out of budget at entity 15 in hard tier
- **Fix**: generate mixed-tier data, especially hard. Add "skip low-importance" reasoning.

**2. Contradiction detection not taught (Maintenance 25%)**
- Generator DOES generate contradictions (`hybrid_gen.py:234-238`) as ingest events
- But during ingest handling (`hybrid_gen.py:282-327`), model just Writes — never searches existing memory first
- Eval sends contradictions as normal `[DOCUMENTS]` with `is_contradiction: True` metadata (hidden from model, `events.py:332-343`)
- Model never learns: search memory before Write → detect changed value → Edit
- **Fix**: for contradiction ingest events, generate Search→Edit chain instead of blind Write

**3. Trick questions absent → abstention over-trigger (affects ~10% of questions)**
- `hybrid_gen.py:506-535`: ALL abstention questions get "I don't have enough information"
- Eval includes trick retrieval questions (phrased like "do you know X?" but have real GT)
- Model learns: if question seems uncertain → abstain. But trick questions penalize this.
- Eval validation: abstention answer must NOT contain numeric values (`scoring.py`)
- **Fix**: generate trick questions where entity IS stored but question is phrased ambiguously → model must answer, not abstain

**4. Template reasoning → reasoning axis ceiling (Reasoning 25%)**
- `_build_reasoning()` (`hybrid_gen.py:89-147`): 8 templates, all "From my memory: X. Answer: Y."
- Eval has 20 competency types: synthesis, aggregation, cross_category, conditional, ratio, comparison, multi_hop, outlier, delta, counterfactual, multi_constraint, relationship_*, temporal_*, text_match, enum_filter
- Answer validation by type (`scoring.py`):
  - Int: exact match. Float: ±2% tolerance. Entity: ≥67% keyword overlap. Synthesis: entity+numeric
  - Fails rule → LLM judge fallback (7 models tried in sequence)
- **Fix**: use strong teacher model (Claude/GPT-5.4) for reasoning question responses, or generate competency-specific reasoning chains

**5. Event distribution skew → ingest undertrained (Breadth 30%)**
- Training: question 55% / ingest 20% / correction 18% / noise 7%
- Eval (lite tier): ~40% ingest + ~10% correction + ~40% question + ~10% noise
- Storage Breadth (30%) depends on ingest quality. Model sees 2.75x more questions than ingest.
- **Fix**: rebalance to ~35% question / 30% ingest / 20% correction / 15% noise

### Scoring formula reference
```
composite = 0.30×Breadth + 0.25×Maintenance + 0.25×Reasoning + 0.20×Efficiency
Breadth    = retrieval_correct / retrieval_total
Maintenance = (update_correct / update_total) × min(stored_coverage / 0.5, 1.0)
Reasoning  = reasoning_correct / reasoning_total  (20 competency types)
Efficiency = min(total_correct / write_budget, 1.0)
```

### Answer validation (rule-first, judge-fallback)
- Integer: exact match only (years, counts, employees)
- Float: ±2% relative tolerance
- Entity: tokenize → ≥67% GT keywords present, length ≥50% of GT
- Synthesis: parse "Entity (value)" → match both
- Abstention: must contain refusal phrase, must NOT contain any number
- Judge: sanitizes agent answer (strips VERDICT_ keywords, HTML-escapes), takes LAST verdict match

### Anti-cheating (9 mechanisms)
1. eval_salt: different numeric fingerprints per run
2. Implicit contradictions: entity re-appears with changed value in normal ingest
3. Trick questions: retrieval phrased like abstention, has real GT
4. Noise documents: mention entities but no complete data
5. Adaptive questioning: replaces questions targeting unstored entities
6. Interleaved questions: ~40% appear during ingest phase
7. Format-agnostic validation: strips units, commas, $
8. Prompt injection guards: sanitize answers before judge
9. Budget enforcement: Write/Edit fail gracefully when exhausted

### SFT experiment history

| Version | Data | Correct | Key Finding |
|---------|------|---------|-------------|
| SFT v1 | old format | 0/10 | Learned Write only |
| SFT v2b | 480 traj | **3/10** | First correct answers; 8 epochs needed |
| SFT v3 | 480 traj | 0/10 | Learned format but lost reasoning |
| GRPO v3 | RL on SFT v3 | 5/10 | Model cheated: answered from context, not memory |

### Key conclusions
1. **v3 data teaches tool format correctly** — context mismatch fixed, edit success high
2. **SFT ceiling ~4-6/10** — teaches mechanics but not strategy (triage, contradiction detection, reasoning)
3. **GRPO is likely needed** for Reasoning + Efficiency optimization — MemoryEnv ready
4. **v4 SFT data improvements** can raise ceiling by fixing gaps 1-5 above — worth one more SFT round before GRPO

## Data Pipeline
- Generator: `scripts/memorygym_hybrid_gen.py`
- Canonical: `data/canonical/memorygym.jsonl`
- RL env: `MemoryEnv` class with binary/shaped rewards, compatible with verl/slime adapters
