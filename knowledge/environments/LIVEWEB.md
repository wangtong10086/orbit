# LIVEWEB Environment

## Key Facts
- Web interaction/browsing evaluation via liveweb-arena Docker container
- Format: OpenAI function calling (tool_calls with goto/click/type/stop etc.)
- Eval uses LLM validator to compare agent answers vs ground truth
- **5-step observation window**: agent only sees last 5 steps in "Recent Actions"
- Each step is independent LLM call (system + user), NOT multi-turn conversation
- **NO reasoning-parser** — `--reasoning-parser qwen3` confirmed harmful (A/B v2.17)

## Eval Architecture
- **Agent**: receives accessibility tree + task prompt, outputs tool_calls
- **Actions**: goto, click, click_role, type, type_role, press, scroll, view_more, wait, stop
- **Scoring**: LLM validator (0.0-1.0) per subtask, arithmetic mean across subtasks. ≥0.8 = correct.
- **Plugins (active)**: coingecko (8), taostats (10), stooq (9), hackernews (4), hybrid (8)
- **GT collection**: on-the-fly via `on_observation` callback — only for pages agent visits
- **Detail > List**: detail page GT always overrides list page GT (priority rule)
- **Disabled**: weather, openlibrary, arxiv, openmeteo

## Current Data: v3 REGENERATED (2026-03-29)

**19,776 entries** — Teacher Bot v2 composite-only. Single-step format.

| Property | Value |
|----------|-------|
| Total entries | 19,776 |
| Format | **Single-step** (3 msgs: system→user→assistant+tool_call) |
| Subtask distribution | 2-sub: 7,442 / 3-sub: 7,216 / 4-sub: 5,118 |
| Action distribution | goto: 16,738 / stop: 3,038 |
| Unique template combos | 1,993 |
| Active plugins | coingecko, hackernews, hybrid, stooq, taostats |
| Char length | min 1,354 / median 6,369 / p95 21,924 / max 23,481 |
| All < 32k seq_len | ✅ (max 23k chars ≈ 7k tokens) |
| ms-swift compatible | ✅ (no tool messages, strict user↔assistant) |
| Tools at top level | ✅ (10 browser actions) |
| `<think>` tag | 0% |
| HF synced | 2026-03-29 |

### Format Details
- Each entry = one decision step (goto or stop)
- System prompt: identical to eval (includes Tips + "detail pages" hint)
- User prompt: page state + accessibility tree + Recent Actions + Working Memory + step counter
- Assistant: tool_call (goto with memory_patch, or stop with answers)
- **No multi-turn**: no tool response messages. Matches eval's single-turn LLM call.
- All entries pass `forge data audit`

### Known Issues
- stooq only 408/19,776 entries (2%) — local cache incomplete, stooq composite generation slow
- hybrid over-represented (15,746 plugin appearances) — limited by 5 active plugins

## Eval Performance (v2.25 = 27.76, best ever)

### Per-Site Accuracy (v2.25 ckpt300, 83 samples)
| Site | Accuracy | Trend |
|------|----------|-------|
| HackerNews | 42.9% | 0%→43% (data diversity worked) |
| Stooq | 28.6% | 10%→29% |
| CoinGecko | 25.0% | 12%→25% |
| Taostats | 13.7% | structural eval issue |

### Failure Mode Breakdown
| Cause | % | Fixable by data? |
|-------|---|-----------------|
| Wrong answer extracted | 38% | Partially (seq_len helps) |
| Visited wrong pages | 19% | Entity diversity helps |
| Didn't visit required page | 10% | More navigation examples |
| Taostats AG Grid broken | ~15% | No — eval infra issue |
| CAPTCHA/timeout | 18% of samples | No — eval infra issue |

### Score Prediction (next training)
- seq=8k QLoRA (same config): 28-32
- seq=16k QLoRA: 33-38
- seq=32k full FT: 35-45

## Data Generation
- **Method**: Teacher Bot v20 (deterministic, no LLM)
- **Code**: `scripts/teacher_generate.py` on training branch (unango/liveweb-arena)
- **Cache**: `/var/lib/liveweb-arena/cache/` on m1+m2. Local copy at `/tmp/lw_cache/cache/`
- **Local generation**: Requires `liveweb-arena` package + Playwright. Cache at `/tmp/lw_cache/cache/`

## Known Issues

### Taostats AG Grid (eval-side, not data)
- Playwright doesn't render AG Grid virtual tables in eval
- Accessibility tree shows "No Rows To Show" — model can't read data
- Training data has populated trees (from cache api_data), but eval has empty trees
- Impact: ~33% of subtasks affected, 14% accuracy

### Stooq Symbol Case (FIXED)
- Cache stores uppercase (`AAPL.US`), templates use lowercase (`aapl.us`)
- Fix deployed on m1+m2 (49 entries lowercased)

### Entity Diversity Ceiling
- Only 66 stooq symbols, 39 CG coins, 238 unique URLs
- Expanding requires new cache collection on m1/m2
- Missing: `cadusd` stooq symbol

## Improvement Priorities
1. **seq_len=16k/32k** — biggest lever (66-97% entries complete vs 28%)
2. **Entity diversity** — more stooq/CG entities via cache expansion on m1/m2
3. **Taostats eval fix** — AG Grid rendering (not data role's scope)
4. **CAPTCHA mitigation** — eval infra (not data role's scope)
