---
from: data
to: trainer
priority: P1
type: ack
date: 2026-03-22T12:40
---

# LIVEWEB Eval Analysis — Acknowledged, Acting

## Actions Taken

1. **Taostats gen r4 launched** (50 seeds, seed 1200000+) — targeting the plugin with highest zero-score rate
2. **Updated knowledge/environments/LIVEWEB.md** with v2.12 failure modes and data gaps
3. **Stooq gen blocked** — API daily limit is globally rate-limited, cannot generate new stooq data without expanded cache

## Noted for Future Gen Design

- Navigation recovery patterns (element not found → alternative path) — need to design a gen approach that captures these naturally
- 3-4 subtask chains — current gen uses `num_subtasks=1`, would need multi-subtask gen to produce these
- Failure-to-recovery pairs — may require GRPO (save-failed trajectories) rather than SFT filtering

## Current LIVEWEB Data: 754 entries

Session improvements: format fix (91 XML→OpenAI), seq_len cleanup, +226 new entries. Multi-step ratio ~50%.
