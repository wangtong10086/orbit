# LIVEWEB Environment

## Key Facts
- Web interaction/browsing evaluation via liveweb-arena Docker container
- Format: OpenAI function calling (tool_calls with goto/click/type/stop etc.)
- Eval uses LLM validator to compare agent answers vs ground truth
- **5-step observation window**: agent only sees last 5 steps in "Recent Actions"
- Each step is independent LLM call (system + user), NOT multi-turn conversation
- **NO reasoning-parser** — confirmed harmful (A/B v2.17)

## Eval Architecture
- **Agent**: receives accessibility tree + task prompt, outputs tool_calls
- **Actions**: goto, click, click_role, type, type_role, press, scroll, view_more, wait, stop
- **Scoring**: LLM validator (0.0-1.0) per subtask, arithmetic mean across subtasks. ≥0.8 = correct.
- **Plugins (active)**: coingecko (8), taostats (10), stooq (9), hackernews (4), hybrid (8)
- **Disabled**: weather (permanent), openlibrary, arxiv, openmeteo (may enable later)
- **Eval image**: self-built from `repos/liveweb-arena` (unango/training branch)

## Current Data: v4 (2026-03-30)

**30,000 entries** — composite-only, single-step format, stooq+hackernews prioritized.

| Property | Value |
|----------|-------|
| Total | 30,000 |
| Format | Single-step (3 msgs: system→user→assistant+tool_call) |
| Subtask types | Composite 2/3/4 only |
| Plugins | hybrid 22.7%, hackernews 22.2%, taostats 18.6%, coingecko 18.5%, stooq 18.1% |
| Unique templates | 3,338 |
| Max/template | 64 |
| Char length | max 23k (all < 32k seq_len) |
| ms-swift | ✅ compatible (no tool messages) |
| HF synced | 2026-03-30 |

## Eval Performance

### v2.28 ckpt1200 = 39.66 (best)
| Plugin | Score | Correct (≥0.8) | n |
|--------|-------|----------------|---|
| taostats | 49.2 | 5/23 | 23 |
| coingecko | 43.3 | 3/24 | 24 |
| hackernews | 33.9 | 2/20 | 20 |
| stooq | 32.1 | 2/25 | 25 |

Progression: ckpt200=25.2 → ckpt600=38.5 → ckpt800=37.6 → ckpt1200=39.7

### Failure Modes
- 24% zero score (7 quick fails <15s, 8 slow fails >30s)
- 63% partial (model solves some subtasks but not all)
- 13% correct

## Data Generation
- **Method**: Teacher Bot v2 composite-only (`TeacherGenerator(include_plugins=[...])`)
- **Code**: `repos/liveweb-arena/liveweb_arena/training/teacher/` (unango/training branch)
- **Cache**: `/tmp/lw_cache/cache/` locally
- **Bug tracker**: `knowledge/liveweb_teacher_bot_bugs.md`

## Known Eval Issues
- **Taostats AG Grid**: Playwright doesn't render virtual tables → empty accessibility tree → low accuracy
- **CAPTCHA/timeout**: ~8% of samples fail to load
