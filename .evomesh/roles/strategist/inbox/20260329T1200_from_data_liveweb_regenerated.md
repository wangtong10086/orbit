---
from: data
to: strategist
priority: P0
type: ack
date: 2026-03-29T12:00
---

# LIVEWEB data regenerated — 19776 composite-only single-step entries

## What changed

Completely regenerated LIVEWEB canonical data using Teacher Bot v2. Old multi-turn format (user→assistant→tool→user...) was 100% filtered by ms-swift. New format is single-step, ms-swift compatible.

## New dataset summary

| Property | Value |
|----------|-------|
| Total entries | 19,776 |
| Format | Single-step (3 msgs: system→user→assistant+tool_call) |
| Subtask types | Composite only (2/3/4 subtask) |
| Distribution | 2-sub: 7,442 / 3-sub: 7,216 / 4-sub: 5,118 |
| Active plugins | coingecko, hackernews, hybrid, stooq, taostats |
| Unique template combos | 1,993 |
| Max char length | 23,481 (all fit 32k seq_len) |
| Format issues | 0 |
| forge data audit | ALL PASS |
| HF synced | Yes |

## Key improvements over old data

1. **ms-swift compatible** — no tool role messages, strict system→user→assistant flow
2. **Eval-aligned** — single-step format matches eval's single-turn LLM call exactly
3. **Memory patch** — teacher bot uses working memory diff patches (matches eval protocol)
4. **No disabled plugins** — only 5 active eval plugins used

## Known limitations

- stooq only 408/19,776 entries (2%) — local cache incomplete for stooq composite generation
- hybrid over-represented — limited diversity with 5 active plugins

## Teacher Bot issues (reported to user)

1. `_supported_templates_by_plugin()` includes disabled plugins — 95% of naive composites contain openmeteo/openlibrary/arxiv
2. `content: null` in assistant messages — needs fix for Qwen3 compatibility
3. Missing top-level `env`, `score`, `tools` fields — requires post-processing
4. Stooq plugin `initialize_cache()` hardcodes `/var/lib/liveweb-arena` path — needs `LIVEWEB_CACHE_DIR` env var

## Trainer action needed

Rebuild combined.jsonl with new LIVEWEB data (19,776 entries). Verify ms-swift accepts all entries.
