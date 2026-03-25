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
- Synced from work1 (4599 pages)
- Stooq normalize_url() deployed for aapl↔aapl.us resolution
