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
- **Scoring**: agent answer vs ground truth via LLM validator (0.0-1.0), geometric mean across subtasks
- **Plugins (active)**: coingecko (8), taostats (10), stooq (7+), hackernews (4), hybrid (8)
- **Not covered by teacher**: openlibrary (4), arxiv (5), openmeteo (4) — cache incomplete
- **Disabled**: weather (6 templates)

## Current Data: v12 SINGLE-TURN (2026-03-25)

**12054 entries** from 2627 trajectories. Each step = independent `system + user + assistant`.

| Property | Value |
|----------|-------|
| Total entries | 12054 |
| Source trajectories | 2627 (2-sub 57%, 3-sub 23%, 4-sub 21%) |
| goto steps | 9427 |
| stop steps | 2627 |
| Think blocks rendered | 12054/12054 (100%) |
| Total chars | 69M (1.2x the old multi-turn 57M) |
| Actions | goto + stop only |

### CRITICAL: Why Single-Turn

Qwen3 chat template only renders `<think>` for assistant messages AFTER `last_query_index` (the last real user message). In LIVEWEB multi-turn data:
- Each step has a `user` observation message → pushes `last_query_index` forward
- Intermediate goto steps are BEFORE `last_query_index` → `<think>` silently dropped
- Only the final stop step gets thinking rendered

**This does NOT affect NAVWORLD** — NW uses `role: "tool"` between steps, which the template skips when computing `last_query_index`.

Single-turn format (system + user + assistant per entry) ensures `last_query_index=1` and assistant at index 2 > 1 → thinking always rendered.

### Data Generation

```bash
# On GPU machine (m1):
cd /root/liveweb-arena-teacher
python3 scripts/teacher_generate.py --output-dir out_s2 --seeds 1-1000 --num-subtasks 2
# Then: convert multi-turn → single-turn, filter bad answers + dedup
```

Cache required at `/var/lib/liveweb-arena/cache/` (deployed to m1 and m2).

## Think Chain Design

Each `<think>` block contains structured reasoning:

**Planning step:** `I need to answer: ... Next: URL Reason: ...`
**Data extraction:** `Current page: ... I can see: ... Working Memory: ...`
**Final computation:** `All data collected: ... Comparing: ... Answer: ...`

## Quality Characteristics

**Strong points:**
- stooq/coingecko steps: precise tree references
- Working Memory accumulates across steps
- Multi-subtask: cross-site navigation
- Zero format issues, zero bad answers

**Known limitations:**
- Only goto+stop actions — no click/type/scroll
- HN/taostats aggregation steps: thinking less specific
- OpenLibrary/arxiv/openmeteo: no cache, no training data

## Training Format
- Canonical `data/canonical/liveweb.jsonl` — single-turn OpenAI tool_calls
- Each entry: `{"messages": [system, user, assistant], "env": "LIVEWEB", "score": 1.0}`
- All entries fit seq_len=8192

## Cache Setup
- Deployed at `/var/lib/liveweb-arena/cache/` on m1 and m2
- **Cache v4**: 4528 real pages (all with real HTML + accessibility_tree + api_data)
- Stooq normalize_url() deployed for aapl↔aapl.us resolution
- Local backup: `data/cache_backup/cache_v4_real.tar.gz` (507MB)
- 38 stooq + 36 coingecko + taostats + HN fully verified
- OpenLibrary still uncacheable (429 rate limiting)

## v2.21 Eval Analysis (baseline before v13 data + cache v4)

**Score: 12.95 (100 samples, 30 errors, 70 valid, valid_mean=18.5%)**

### Error breakdown (30/100)
- 14× CAPTCHA/challenge (stooq — fixed by cache v4)
- 6× CoinGecko 404 (fixed by cache v4)
- 4× OpenLibrary 429 (still unfixable)
- 3+2× CoinGecko API errors (fixed by cache v4)

### Zero-score analysis (35/70 valid = 50%)
- **Nav loops**: model revisits same URLs, accumulates `no_progress` + `repeated_url` penalties
- Example: 47/50 steps with `no_progress`, 38 with `repeated_url`
- Even top-scoring tasks (0.50-0.52) show nav loop behavior
- Root cause: model doesn't stop efficiently, gets stuck in URL repetition

### Score ceiling
- Max score: 0.52 — model gets ~half subtasks correct
- 16/35 non-zero tasks score 0.50-0.70
- No task scores above 0.70 — room for improvement in answer accuracy

## v2.23 Eval Analysis (v13 single-turn data + cache v4, noreason mode)

**m2 final: 13.96 (99 samples, 7 errors, 92 valid, valid_mean=15.02%)**

### Cache fix validated
- Error rate: 30% → 7% ✅ (cache v4 working)
- Remaining errors: 5× CAPTCHA + 2× API failure

### NEW #1 Issue: Null Ground Truth (41% of all answers)
- 264 total answers, 110 (41%) have GT=null → auto score 0.0
- 89/110 null GTs are in zero-score tasks → **this is the primary score killer**
- **36 null-GT tasks have ZERO cache misses** — cache is fine, agent just doesn't visit all required pages
- Root cause: model stops after visiting 2-4 pages, but multi-subtask tasks need ALL required pages visited for GT collection
- GT is collected on-the-fly via `on_observation` callback — only available for pages agent actually visits

### Behavior change vs v2.21
- v2.21: long nav loops (50 steps, stuck in repetition)
- v2.23: short episodes (3-11 steps), model stops quickly but gives wrong/unverifiable answers
- The single-turn format fixed nav loops but created premature stopping

### Missing cache entries causing issues
- Stooq: `^ftse`, `^n225`, `usdgbp`, `snap.us`, `^cac40` — agent navigates to uncached symbols
- CoinGecko: agent searches for `google`, `apple`, `tesla` (stock names, not crypto) — wrong site
- Model hallucination: navigates to non-existent URLs like `coingecko.com/en/coins/walmart`

### Improvement vectors
1. **Anti-premature-stop**: training data needs examples showing agent visiting ALL required pages before stopping
2. **Multi-site navigation patterns**: ensure training trajectories demonstrate visiting 2-4 different sites per task
3. **Reasoning parser**: `noreason` mode may corrupt tool calls — need to test with `--reasoning-parser qwen3`
4. **More symbol coverage**: cache needs `^ftse`, `^n225`, `^ks11`, `usdgbp`, `gbpeur` etc.
