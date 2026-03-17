# LIVEWEB Environment Design Improvement Suggestions

> 2026-03-14 — Based on data analysis and source code review

## Core Problem

LIVEWEB current conversation median is 155K chars (~39K tokens), **98% is repeated accessibility tree**.

- Exceeds training seq_len (4K-8K), model cannot learn complete strategies after truncation
- Severely imbalanced with other environments: GAME ~1K tokens/entry, NAVWORLD ~3K tokens/entry
- Of 1029 DDB entries, only 185 (18%) are ≤16K tokens — very low trainable proportion
- Led to LIVEWEB distillation being paused, unable to participate in training iterations

## Data Status

| Metric | Value |
|--------|-------|
| DDB sample count | 1,029 |
| Median chars | 155,432 |
| Median est. tokens | ~39K |
| ≤4K tokens | 17 (1.7%) |
| ≤8K tokens | 49 (4.8%) |
| ≤16K tokens | 185 (18%) |
| >16K tokens | 844 (82%) |

## Suggestion 1: Compress Accessibility Tree (Highest Impact) 🔴

**Current state**: Each step sends the full DOM tree ~11,600 chars, including many non-interactive decorative elements.

**Suggestion**:
- Remove whitespace/purely decorative elements (40-60% of the tree)
- Keep only interactive elements (link, button, input, select), use summaries for plain text
- Abbreviated format: `[link] "Login" → /account` instead of full nested paths

**Expected**: 11,600 → 3,000-4,000 chars/step (65% compression)

## Suggestion 2: Page Deduplication — Send Deltas Instead of Full Pages 🔴

**Current state**: When consecutive steps are on the same page (click failed, retry), the same 11K tree is sent 3-5 times.

**Suggestion**: When URL + title unchanged, only send the changed portion:
```
[Page unchanged from Step 3. Action failed: element not found]
```

**Expected**: 50-70% redundancy reduction

## Suggestion 3: Switch to Standard Tool Calling Format

**Current state**: Custom JSON-in-message format:
```json
{"action": {"type": "click", "params": {"selector": "..."}}}
```

**Suggestion**: Switch to OpenAI function calling standard format (`tool_calls` + `tool` role):
```json
// assistant
{"role": "assistant", "content": null, "tool_calls": [
  {"id": "call_001", "type": "function", "function": {"name": "click", "arguments": "{\"selector\": \"...\"}"}}
]}
// tool
{"role": "tool", "content": "Success", "tool_call_id": "call_001"}
```

**Rationale**:
- Unified with NAVWORLD format, model only needs to learn one format
- Qwen3 natively supports tool_call, no need to learn custom JSON parsing
- Reduces parse errors

## Suggestion 4: Assistant Messages Should Not Be Empty

**Current state**: In SFT data, assistant messages are almost all 0 chars, actions are hidden in tool results. Model cannot learn any reasoning process.

**Suggestion**: Assistant messages should include:
1. Brief reasoning (1-2 sentences): why this action was chosen
2. The action itself: tool_call or JSON action

**Example**:
```
The current page shows a cryptocurrency list; need to find Bitcoin's detail page. Clicking the "Bitcoin" link to enter.
```

## Suggestion 5: Step History Compression

**Current state**: Keeps the full response of the last 5 steps (500 chars cap each).

**Suggestion**:
- Old steps only keep `action_type + result` (e.g., `click → success`)
- Keep the most recent 2 steps in full

## Expected Results

| Metric | Current | After Improvement |
|--------|---------|-------------------|
| Median tokens/entry | ~39K | **8-10K** |
| ≤8K tokens ratio | 5% | **60-70%** |
| Trainable data ratio | 18% | **70%+** |
| Format | Custom JSON | Standard tool_call |

**Priority**: Suggestions 1 + 2 have the highest impact; alone they can cut token count by 65-75%. Suggestions 3 + 4 improve training quality.

## Source Code Reference

- `liveweb-arena/env.py` — Main orchestration (line 1339)
- `liveweb-arena/liveweb_arena/core/browser.py` — Accessibility tree generation (lines 462-620)
- `liveweb-arena/liveweb_arena/core/agent_policy.py` — Action parsing and prompt building
- `liveweb-arena/liveweb_arena/core/agent_loop.py` — Agent execution loop
- `liveweb-arena/liveweb_arena/core/reward.py` — Scoring logic
