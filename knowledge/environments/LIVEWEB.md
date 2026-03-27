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

## Current Data: v20 AUDITED (2026-03-27)

**17,108 entries** — downsampled from 25,205. Capped ≤200 per template. 0% think.

| Property | Value |
|----------|-------|
| Total entries | 17,108 |
| Composite templates | 9,999 (4,161 unique combinations) |
| Single templates | 7,109 (35 types, capped at 200 each) |
| `<think>` tag | 0% — stripped per user directive |
| Tools defined | All 10 eval BROWSER_ACTIONS |
| Tools used | goto + stop only (by design) |
| Domains | 4 (stooq, coingecko, taostats, hackernews) |
| Unique URLs | 238 |
| Unique page snapshots | 34,035 |
| Entity coverage | 66 stooq symbols, 39 CG coins |
| Seq_len coverage | 28% fit 8k, 66% fit 16k, 97% fit 32k |
| Format alignment | ✅ system prompt, stop format, answer keys all match eval |
| HF synced | 2026-03-27 |

### Format Details
- System prompt: identical to eval (includes Tips + "detail pages" hint)
- Stop action: `{"answers": {"answer1": "...", ...}}` JSON string — matches eval parser
- Answer types: short_text 41%, pipe_delimited 22%, pure_number 21%, dollar 6%, json 5%
- All entries pass `forge data audit`

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
