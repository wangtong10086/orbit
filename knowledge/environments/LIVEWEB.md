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

## Improvement Directions

### Environment-Side Improvements (requires upstream changes)

1. **Compress accessibility tree** (highest impact): Each step sends ~11,600 chars full DOM. Remove non-interactive decorative elements, keep only links/buttons/inputs. Expected: 11,600 → 3,000-4,000 chars/step (65% compression).
2. **Page deduplication**: When URL+title unchanged between steps, send delta instead of full page. Expected: 50-70% redundancy reduction.
3. **Switch to standard tool calling format**: Replace custom JSON-in-message `{"action":{"type":"...","params":{...}}}` with OpenAI function calling (`tool_calls` + `tool` role). Unifies with NAVWORLD format, reduces parse errors.
4. **Add assistant reasoning**: Currently assistant messages are ~0 chars (actions hidden in tool results). Should include 1-2 sentence rationale.
5. **Step history compression**: Old steps keep only `action_type + result`, recent 2 steps in full.

Expected combined result: median tokens/entry 39K → 8-10K, trainable ratio 18% → 70%+.

Source: `liveweb-arena/env.py` (line 1339), `liveweb_arena/core/browser.py` (lines 462-620), `liveweb_arena/core/agent_policy.py`.

### Our-Side Improvements
- Continue DDB accumulation (997+ samples, growing)
- Retry distillation after upstream compression
- DashScope models cannot complete browser tasks (0% success rate) — DDB only for now
