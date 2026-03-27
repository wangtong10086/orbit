# LIVEWEB Environment

## Key Facts
- Web interaction/browsing evaluation via liveweb-arena Docker container
- Format: OpenAI function calling (tool_calls with goto/click/type/stop etc.)
- Eval uses LLM validator to compare agent answers vs ground truth
- **5-step observation window**: agent only sees last 5 steps in "Recent Actions"
- Each step is independent LLM call (system + user), NOT multi-turn conversation

## Eval Architecture
- **Agent**: receives accessibility tree + task prompt, outputs tool_calls
- **Actions**: goto, click, click_role, type, type_role, press, scroll, view_more, wait, stop
- **Scoring**: agent answer vs ground truth via LLM validator (0.0-1.0), arithmetic mean across subtasks
- **Plugins (active)**: coingecko (8), taostats (10), stooq (7+), hackernews (4), hybrid (8)
- **GT collection**: on-the-fly via `on_observation` callback — only for pages agent visits
- **Disabled**: weather (6 templates), openlibrary (429), arxiv, openmeteo

## Current Data: v20+HN SINGLE-TURN (2026-03-27)

**10799 entries** = 9999 base (composite) + 800 HN diversity (4 templates x 200 seeds).

| Property | Value |
|----------|-------|
| Total entries | 10799 |
| Base entries (v20) | 9999 — no `<think>` tags (empty assistant content before tool_calls) |
| HN entries (+800) | 800 — WITH `<think>` tags (deterministic reasoning) |
| `<think>` tag | 7.4% (800/10799) — only in new HN data |
| Tools defined | All 10 eval BROWSER_ACTIONS |
| Tools used | goto + stop only (by design — teacher bot approach) |
| HN templates | news_summary, multi_condition_filter, extrema_comparison, category_comparison |
| HF synced | 2026-03-27 |

### Data Generation
- **Method**: Teacher Bot composite (deterministic thinking, no LLM)
- **Code**: `scripts/teacher_generate.py` on training branch (unango/liveweb-arena)
- **Cache**: `/var/lib/liveweb-arena/cache/` on m1+m2
- **Pipeline**: raw trajectories → single-turn conversion → strict dedup → quality filter → balance

### Quality Filters Applied
1. Trajectories must have: stop + real_pages >= n_sub + steps >= n_sub+1
2. Dedup by (URL + content + action) hash — 87% dedup rate
3. Removed 751 premature stop entries (stop before visiting all needed sites)
4. Removed 360 CoinGecko ungrounded entries (think values not in tree)
5. Fixed `<thinking>` → `<think>` tag (Qwen3 compatibility)

## Cache Setup
- **Cache v4**: 4528+ real pages on m1 and m2
- Stooq symbol case: 49 entries lowercased (JSON API returns uppercase, templates use lowercase)
- Stooq normalize_url() for aapl↔aapl.us
- Taostats: 35/128 subnets in tree (AG Grid virtual scrolling limitation)
- Local backup: `data/cache_backup/cache_v4_real.tar.gz` (507MB)

## Root Cause Analysis

### GT Case-Mismatch Bug (verified +22 points)
- Stooq api_data stores symbol as uppercase (`AAPL.US`), templates use lowercase (`aapl.us`)
- GT collector lookup misses → null GT → score=0
- Fix: lowercase cache api_data symbol field (49 entries on m1+m2)
- Verified: score 14→36.8 (6 samples with fix applied)

### Generator Issues Found & Fixed
1. **`<thinking>` tag** → fixed to `<think>` in observation.py + generator.py
2. **Plugin URL normalization** → fixed in `_load_from_disk()` (commit 2c02500)
3. **Taostats table rendering** → wait_for_selector + js_render_wait (commit bba6cf7)
4. **87% dedup rate** → template combination space limited (needs more templates)
5. **CoinGecko SPA tree** → tree includes homepage header but detail data is present

### Remaining Risks
- Taostats only 35/128 subnets in tree (ranking questions for lower subnets may fail)
- `--reasoning-parser qwen3` not tested (eval uses noreason mode)
