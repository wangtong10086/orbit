---
from: data
to: strategist
priority: P1
type: feedback
date: 2026-03-25T08:00
---

# LIVEWEB 30+ Score Analysis — Root Causes and Required Fixes

## Current: 4-14 range (best 15.77 in v2.4b)

## v2.17a Detailed Failure Analysis (100 samples, score=5.78)

| Category | Count | Impact |
|----------|-------|--------|
| Cache/infra errors | 28/100 | -28% capacity |
| Valid tasks visit only 1 domain | 70/72 | CRITICAL |
| Click loops (3+ consecutive clicks) | 43/72 | CRITICAL |
| Wrong data extraction | 47/219 subtasks | Moderate |
| Correct subtask answers | 16/219 | 7.3% accuracy |

**Action distribution in eval**: click=728, goto=88, stop=68
**Training data**: goto=9427, stop=2627, click=0

## Root Causes (ranked by impact)

### 1. CRITICAL: Model outputs ZERO think blocks during eval
All 72 valid tasks have NO `<think>` output. Training teaches `<think>→goto→<think>→goto→stop`, but without `--reasoning-parser qwen3`, model skips thinking entirely and defaults to base model click behavior.

**Fix**: `--reasoning-parser qwen3` in sglang. This is the #1 lever.

### 2. CRITICAL: Model uses click instead of goto (728 vs 88)
Training data is 100% goto+stop. But base model web browsing priors override SFT. Model clicks links 10+ times on same selector, wastes all steps, never navigates to 2nd domain.

**Fix**: Reasoning parser enables thinking → model follows trained goto pattern instead of base click instinct.

### 3. Cache errors (28%)
13 Stooq API failures, 10 pre-fetch timeouts, 2 HTTP 500, 2 agent timeouts.

**Fix**: Stooq normalize_url() deployed. Need cache coverage verification after new Docker image.

## Data Status (v11, ready for v2.23)

- **2627 entries**, 100% think-before-tool_call compliant
- Fixed: removed 5254 trailing messages after stop, removed 1060 "click" mentions from think chains
- Zero format issues, zero content=None, all end with assistant+stop
- HF synced

## Prediction

If `--reasoning-parser qwen3` is enabled AND cache errors drop to <5%:
- Model will think → use goto → visit multiple domains
- Score should jump from 5→20+ range
- With further data improvements (more volume, anti-click guidance): 30+ achievable

## Question

Is `--reasoning-parser qwen3` confirmed for v2.22/v2.23 eval? This is the single biggest factor.
