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

### Trailing User Message Bug (v4 fix)
- 444 entries had last message with role=user (diff content)
- Model learns to predict user output instead of generating assistant reply
- **Fix**: Removed trailing user messages from all SWE-SYNTH entries

### Length Issue
- Most raw DDB samples >16K chars (~32K median)
- At max_seq_len=4096, most samples get truncated to conversation beginning (useless)
- Relaxed to 32K chars recovered 437 entries (from 26 at 16K threshold)
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
- v10: 1350 entries in training mix
- Leaderboard score: ~30-32 points (competitive but not leading)
- No local eval capability

## Improvement Directions
- More high-quality samples (DDB continues accumulating)
- Dedicated SWE-SYNTH focused training run
- DPO alignment (258 pairs available)
- Match system prompt exactly to eval environment
- Consider longer max_seq_len for SWE-SYNTH-heavy runs
