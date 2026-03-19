# SWE-SYNTH Environment

## Key Facts
- Multi-turn code repair/debugging evaluation
- Format: THOUGHT (free text reasoning) + single bash code block
- Binary scoring: 0 or 1 (pass/fail)
- Does NOT support think tags (conflicts with THOUGHT format)
- Most samples are very long (>16K chars)
- Cannot evaluate locally (needs breaker service to pre-generate tasks)
- Only verifiable through leaderboard deployment

## Format Requirements
- System prompt + multi-turn structure
- Assistant uses THOUGHT prefix for reasoning, then a bash code block
- No `<think>` tags allowed (would conflict with THOUGHT format)

## Data Issues

### Think Tag Contamination — RESOLVED (2026-03-18)
- Original: 334/1351 entries (24.7%) contained `<think>` tags
- **Fixed**: 368 contaminated entries removed. Canonical now 983 clean entries, 0 think tags.
- File ownership issue resolved (delete + redownload workaround)

### Trailing User Message Bug (v4 fix)
- 444 entries had last message with role=user (diff content)
- Model learns to predict user output instead of generating assistant reply
- **Fix**: Removed trailing user messages from all SWE-SYNTH entries

### Length Issue
- Most raw DDB samples >16K chars (~32K median)
- At max_seq_len=4096, most samples get truncated to conversation beginning (useless)
- Relaxed to 32K chars recovered 437 entries (from 26 at 16K threshold)
- Only 2.4% fit in 4096 tokens, 46% fit in 8192 tokens (2026-03-18 audit)
- Still a constraint on usable data volume

## Data
- DDB source: 11,594 total samples, avg score 0.335
- Usable (score >= 0.5, <= 32K chars): ~437-1350 entries (varies by extraction pass)
- v10 training: 1350 entries, 10.2% of total mix
- DPO pairs available: 258

## Evaluation
- Cannot run locally — needs external breaker service
- Only verifiable via leaderboard after model deployment
- Leaderboard scores: our best ~30-32 points, top competitor (AnastasiaFantasy) ~44 points

## Current Best / Status
- Canonical: 983 clean entries (think tags removed, seq=8192 compatible)
- v2.1 training: 983 entries at seq=8192
- Leaderboard top: affshoot 43.43, wisercat 42.42 (Block 7777474)
- No local eval capability

## Improvement Directions
- More high-quality samples (DDB continues accumulating)
- Dedicated SWE-SYNTH focused training run
- DPO alignment (258 pairs available)
- Match system prompt exactly to eval environment
- Consider longer max_seq_len for SWE-SYNTH-heavy runs
