# LIVEWEB Environment

## Key Facts
- Web interaction/browsing evaluation via liveweb-arena Docker container
- Format: OpenAI function calling (tool_calls with goto/click/type/stop etc.)
- Eval uses LLM validator to compare agent answers vs ground truth
- Leaderboard scores: ~14-19 points (everyone in 13-19, relatively flat)
- **v2.2: 6.83** (format bug), **v2.3: 8.62** (format fixed), **v2.4b: 15.77** (best, seq=16384), **v2.7: 13.76** (seq=8192)

## Eval Architecture
- **Agent**: receives accessibility tree + task prompt, outputs tool_calls
- **Actions**: goto, click, click_role, type, type_role, press, scroll, view_more, wait, stop
- **Scoring**: agent answer vs ground truth via LLM validator (0.0-1.0)
- **Plugins (5 usable)**: coingecko, stooq, hackernews, taostats, hybrid
- **Unusable**: arxiv (Docker fail), openmeteo (Docker fail), openlibrary (agent score=0)
- **Disabled**: weather
- **num_subtasks=1** in production (infer.py), same as our gen script

## Training Format
- Canonical `data/canonical/liveweb.jsonl` stores **OpenAI tool_calls format** (raw)
- `forge rental prepare-data` calls `_normalize_tool_calls_qwen3()` to convert to Qwen3 native
- **CRITICAL**: canonical must NOT contain `<tool_call>` XML — only OpenAI format
- No compression needed: all entries fit seq=16K

## Data Generation: `scripts/liveweb_real_gen.py`

```bash
# With cache (required for stooq/hybrid)
python3 liveweb_real_gen.py -n 30 --plugin hybrid -o out.jsonl \
  --cache-dir /root/liveweb_full_cache --model gpt-5.4 \
  --api-key $KEY --base-url $URL --start-seed $RANDOM_SEED

# Without cache (hackernews/taostats/coingecko)
python3 liveweb_real_gen.py -n 30 --plugin hackernews -o out.jsonl \
  --model gpt-5.4 --api-key $KEY --base-url $URL
```

Features: --cache-dir mounts volume, cache TTL permanent, auto-fix last msg, random seeds to avoid dupes.

## Plugin Viability (gpt-5.4)

| Plugin | Success Rate | Score | Cache needed | Canonical |
|--------|-------------|-------|--------------|-----------|
| coingecko | ~50% | 1.0 | No | 317 |
| stooq | ~60% | 1.0 | Yes (API limit) | 68 |
| hackernews | ~50% | 0.7-0.94 | No | 51 |
| taostats | ~34% | 0.5-1.0 | No | 23 |
| hybrid | ~33% | 1.0 | Yes (needs stooq) | 0 (stooq API blocked) |
| openlibrary | — | 0.0 | — | Not usable |
| arxiv | 0% | — | — | Docker fail |
| openmeteo | 0% | — | — | Docker fail |

## v2.7 Eval Analysis (score=13.76)
- 100 samples: 34 infra errors (stooq API), 46 score=0 (wrong answer), 20 score>0
- score=0.5 most common (13/20) — partial correct on multi-subtask
- Excluding infra errors: 66 valid, mean=13.76
- Gap vs competitors (15-19): model extracts wrong info on 46/66 valid samples

## Current Data: 464 entries
coingecko 317 (68%), stooq 68 (14%), hackernews 51 (10%), taostats 23 (4%), openlibrary 4
Action: goto 52%, stop 31%, click_role 6%, click 4%, type 2%

## Cache Setup
Cache at `repos/liveweb-arena/cache/` → merge `cache/cache/` + `cache/liveweb-arena/cache/` into single dir.
Must include `_plugin_init/stooq_homepage.json` (28 assets) + `_plugin_init/taostats_subnets.json`.
Upload to GPU: `forge rental -m m2 upload cache.tar.gz /root/` → extract to `/root/liveweb_full_cache`.
**Note**: stooq CSV API (`/q/d/l/`) is globally rate-limited. Cache helps page loading but NOT GT validation API calls.
