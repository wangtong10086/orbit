# LIVEWEB Teacher Bot: Required Modifications for 50+ Score

> Status: Reference note
> Authority: Non-normative
> Last reviewed: 2026-04-04
> Use this file for background and deep analysis, not as the primary source of truth.


## Current Architecture

Teacher bot generates training data via:
1. `generator.py`: orchestrates trajectory (goto → goto → ... → stop)
2. `observation.py`: builds message sequences, calls `build_deterministic_thinking()`
3. `teacher_prompts.py`: generates think blocks from template variables
4. `helpers.py`: extracts data from api_data, finds tree evidence

Think blocks are **deterministic** (template-based), not LLM-generated.

## Root Cause of Low Score (24% accuracy)

### Problem 1: Stop step think blocks are empty/vague

**Code path**: `teacher_prompts.py:186-189`
```python
lines.append("The page contains the data needed to answer this question.")
lines.append("After analyzing the page content:")
```

**When triggered**: extraction from api_data fails completely (extraction_keys don't match, fallback keys fail, nested extraction fails).

**Impact**: Model learns "look at page → just give answer" instead of "find specific value in accessibility tree → compute → answer".

### Problem 2: Tree evidence rarely found

**Code path**: `helpers.py:158-219` `_find_tree_evidence()`

This searches for EXACT value matches in the accessibility tree. But:
- Numbers formatted differently: API says `251.64`, tree says `Last 251.64` or `$251.64 USD`
- Percentage formatting differs: API says `0.52`, tree says `0.52%` or `+0.52%`
- Pattern matching is too strict — misses many valid matches

**Impact**: Even when extraction succeeds, tree_evidence is empty → think block doesn't teach the model WHERE to look in the tree.

### Problem 3: Single-entity stop steps skip reasoning

**Code path**: `teacher_prompts.py:216`
```python
lines.append(f"Answer: {ground_truth}")
```

For tasks with only one entity, the think block jumps directly to the answer with no extraction reasoning.

### Problem 4: No computation steps for aggregation questions

Questions like "Calculate the percentage of subnets showing losses" require:
1. Count subnets with negative 24H change
2. Count total subnets
3. Divide and format

But the think block just says: `"Answer: 56.2%"` — no intermediate steps.

## Required Modifications

### Fix 1: Make tree evidence search more robust

**File**: `helpers.py:158-219`

Currently too strict. Need to:
- Search for values with ±formatting variants ($, %, +/-, commas)
- Search for entity names (not just values)
- Allow partial matches (tree line CONTAINS the value string)
- Include 2-3 surrounding lines for context (model learns WHERE in the tree)

### Fix 2: Eliminate vague fallback in stop steps

**File**: `teacher_prompts.py:186-189`

When extraction fails, instead of "The page contains the data needed":
1. Fall back to SEARCHING the accessibility_tree directly for answer-related values
2. If the ground_truth is a number, search the tree for that number
3. Quote the exact tree line where the answer appears
4. If nothing found, log a warning (don't silently degrade quality)

### Fix 3: Add explicit computation in final think blocks

**File**: `teacher_prompts.py:192-216`

For aggregation/computation questions (detected by keywords like "percentage", "how many", "calculate", "total"):
1. List ALL relevant data points from working memory
2. Show the arithmetic step by step
3. Show the formula: `count_matching / total = X / Y = Z%`

Example:
```
Subnets with 24H loss: SN1 (-2.3%), SN5 (-0.8%), SN11 (-1.2%), ... (36 total)
Total subnets: 64
Percentage = 36 / 64 × 100 = 56.25% ≈ 56.2%
Answer: 56.2%
```

### Fix 4: Always reference tree evidence in every step

**File**: `teacher_prompts.py:160-190`

Change: goto steps MUST include at least one quoted line from the accessibility tree showing the extracted value. If tree evidence can't be found, retry with looser matching. If still nothing, quote the first 3 meaningful lines of the tree as context.

### Fix 5: Stop steps must verify data completeness

**File**: `teacher_prompts.py:192-217`

Before generating stop answer, the think block should:
1. List all subtasks and which ones have data collected
2. If any subtask data is missing, acknowledge it (teaches model to navigate more before stopping)
3. For multi-subtask tasks: "I have data for answer1 (AAPL price) and answer3 (BTC volume), but NOT answer2 (EURUSD rate). I need to visit stooq.com/q/?s=eurusd first."

This teaches the model NOT to stop prematurely.

## Expected Impact

| Fix | Addresses | Expected Score Impact |
|-----|-----------|----------------------|
| GT case-mismatch bug | 40+ null GT answers | +15 (already coded) |
| Tree evidence robustness | Vague think blocks | +5-10 (better extraction) |
| Computation steps | Wrong calculations | +5-8 |
| Data completeness check | Premature stopping | +3-5 (reduces null GT) |
| **Combined** | | **28-38 additional points → 42-52 total** |

## Code Change Locations

| File | Lines | Change |
|------|-------|--------|
| `liveweb_arena/core/gt_collector.py` | 308-323 | Case normalization (DONE) |
| `liveweb_arena/core/block_patterns.py` | 17-44 | Stealth Playwright (DONE) |
| `liveweb_arena/plugins/hybrid/utils.py` | 148-167 | Case lookup fix (DONE) |
| `liveweb_arena/training/teacher_prompts.py` | 160-216 | Think block quality |
| `liveweb_arena/training/teacher/helpers.py` | 158-219 | Tree evidence robustness |
| `liveweb_arena/training/teacher/observation.py` | 183-302 | Extraction fallbacks |
