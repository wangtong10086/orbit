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
- Shorter, high-quality synthetic data generation
- Distillation from strong model on shorter tasks
- Consider scripts/liveweb_gen.py for synthetic generation
- DDB data continues accumulating (997+ samples, growing)
- Framework understanding needed for effective distillation
