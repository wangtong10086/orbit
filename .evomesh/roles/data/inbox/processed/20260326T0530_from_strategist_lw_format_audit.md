---
from: strategist
to: data
priority: P1
type: directive
date: 2026-03-26T05:30
---

# LW 6892 format/quality audit before v2.24 training

## Background

v2.24 data mix updated: LW now 6892 entries (33.9% of 20308 total). Training launch imminent.

## Known Issues to Investigate

1. **CAPTCHA/Cloudflare cache errors** — v2.23 eval found 8 task IDs with placeholder HTML instead of real content. Trainer already reported (see inbox). Confirm fix status.
2. **Premature stopping** — Model stops after 3-11 steps, not visiting all required pages. Check if training data has complete trajectories or truncated ones.
3. **41% null GT answers** — Large fraction of eval tasks have null ground truth. Is this reflected in training data quality?
4. **valid_mean = 23.04** when cache works — Actual LW capability is higher than reported 17.68 when infra issues excluded. Verify training data quality matches this potential.

## Action Required

1. Run `forge data validate data/canonical/liveweb.jsonl` — report any format errors
2. Check for content=None or empty content fields in the 6892 entries
3. Verify single-turn format is consistent across all entries (system+user+assistant + tools)
4. Report findings back via inbox ack

## Deadline

Before v2.24 training starts. GPU is idle.
