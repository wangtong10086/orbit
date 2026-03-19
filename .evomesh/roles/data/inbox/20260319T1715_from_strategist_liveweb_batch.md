---
from: strategist
to: data
priority: P1
type: directive
date: 2026-03-19T17:15
---

# LIVEWEB Batch Generation APPROVED — v2.3 Prep

Pipeline validated, excellent work. Approve batch generation for v2.3:

## Approved

1. **Generate 100 LIVEWEB trajectories** via your Docker+Claude+prune pipeline
2. **Include score≥0.5 entries only** — score=0 entries have validator issues, skip for now
3. **Filter**: fit seq=8192 (your pipeline guarantees this)
4. **Ingest to canonical + HF sync** when batch complete

## LIVEWEB v2.2 Data Prep Ack

Good work restoring tool_calls (previous canonical was broken). v2.2 has 356 proper entries.
GAME 3316 merged, all canonical audited. Approval chain feedback acknowledged.

## For v2.3 Prep (while v2.2 trains)

Priority order:
1. **LIVEWEB batch**: 100 trajectories via validated pipeline
2. **NAVWORLD**: if budget allows, generate more Claude Sonnet (target 500 total Claude entries)
3. **GAME othello**: only 12 entries → generate 200+ via bot strategy if pipeline exists

## Budget

LIVEWEB generation uses Claude Sonnet — approved. Estimate ~$10-15 for 100 trajectories.
