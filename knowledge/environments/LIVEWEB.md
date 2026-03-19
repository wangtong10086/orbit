# LIVEWEB Environment

## Key Facts
- Web interaction/browsing evaluation
- Format: free thinking + JSON action object
- Supports think tags
- Cannot evaluate locally (task_id range restriction, needs predefined task set)
- Only verifiable through leaderboard deployment

## Critical Data Problem: Everything Is Too Long
- 844 entries extracted from DDB (score >= 0.5)
- Median length: 145K chars (~36K tokens)
- At max_seq_len=8192: 0 entries usable (all truncated to conversation beginning)
- When included in v3 training (2532 entries, 20.4% share): pure noise, wasted training budget

## Data History
- DDB total: 15,844 samples, avg score 0.172 (very low)
- High quality (>= 0.7, <= 16K): only 3 entries (essentially none)
- v3: included 844 entries (3x weighted = 2532), all too long — removed in v4
- v7+: re-included with heavy filtering, ~437 entries at score >= 0.5 with length cap
- Distillation attempted but failed (framework changed from original)

## Training Inclusion
| Version | Entries | Share | Notes |
|---------|---------|-------|-------|
| v3 | 2532 (3x) | 20.4% | All too long, pure noise |
| v4 | 0 | 0% | Removed entirely |
| v7 | 437 | 9.1% | Re-included with length filter |
| v8 | 437 | 6.2% | Native tool_call format |
| v10 | 437 | 3.3% | Same entries |

## Current Best / Status
- 437 entries in training mix (v7+)
- Leaderboard: ~24 points (everyone is 16-28, relatively flat)
- No local eval capability
- Score improvement hard to verify without deployment

## Dead Ends (attempted, not viable)

### liveweb_gen.py + liveweb_env_patched.py — REMOVED (2026-03-19)
Docker-based distillation pipeline using affinetes SDK + qwen-max. **Why it failed**:
1. **qwen-max 0% success rate** on browser tasks — generates garbage trajectories, not just low quality
2. **Heavy external dependencies**: Docker, TAOSTATS_API_KEY, COINGECKO_API_KEY, CHUTES_API_KEY for validator — fragile, expensive
3. **1229-line monkey-patch** (liveweb_env_patched.py) of upstream env.py — unmaintainable, breaks on upstream updates
4. **Task diversity problem**: eval tests diverse websites, but generation was limited to CoinGecko-style queries
5. **No local eval**: cannot verify generated data improves scores without full leaderboard deployment (~$9/run)
6. **Length problem unsolved**: real eval tasks are ~36K tokens median, seq=8192 truncates everything. `num_subtasks=1` workaround only generates trivial subtasks

### DDB extraction — PARTIALLY VIABLE (current approach)
347 entries from historical eval database, all score=1.0, fit seq=8192. **Limitations**:
- Only 114 unique seeds, 1 system prompt — low diversity
- DDB avg score 0.172 (very low), only ~437/15844 entries usable after filtering
- No new data unless more eval runs happen upstream

## Viable Future Paths

### Phase 3: Claude API distillation (pending upstream compression)
- Claude can complete browser tasks (unlike qwen-max)
- **Blocked by**: accessibility tree too long (~11.6K chars/step → ~36K tokens/trajectory)
- **Unblocks when**: upstream compresses DOM (11.6K → 3-4K chars/step, 65% reduction)
- Upstream improvements needed: DOM compression, page dedup, step history compression
- Expected result after compression: median tokens 39K → 8-10K, trainable ratio 18% → 70%+
- Source refs: `liveweb-arena/env.py:1339`, `liveweb_arena/core/browser.py:462-620`

### Phase 3: RC-GRPO with reward model
- Binary reward (task success/fail) from validator
- Needs Stage 1 expert+failure trajectories — blocked by same length issue
- See `knowledge/training.md` for RC-GRPO data format spec
