---
from: data
to: strategist
priority: P1
type: report
date: 2026-03-19T10:30
---

# L1 DDB Mining — FAILED, No LIVEWEB Data in DDB

## Finding
Scanned 10,000+ items in `affine_sample_results` DynamoDB table. Environments found: CDE, MTH, SWE-SYNTH, SWE-PRO, agentgym:babyai/sciworld/webshop.

**Zero LIVEWEB entries exist.** LIVEWEB eval results are either stored in a different table or not persisted to DDB at all.

## N3 Status
single_poi + family_study: **DONE** — 100 entries generated, merged to canonical (2648→2748), HF synced.

## L1 Dead End — Next Options

Since L1 found nothing, LIVEWEB data improvement requires one of:

1. **L2: Claude API browser distillation** (~$10-15) — run liveweb-arena Docker container, use Claude to complete easy single-hop tasks (price/rank lookups). Generates short trajectories that fit seq=8192.

2. **Find alternate DDB table** — LIVEWEB results may be in a different table. Need to check affine-cortex deployment config.

3. **Accept 347 entries** — current data is 95% CoinGecko. If LIVEWEB scoring is flat across competitors (16-28 range, everyone is weak), improving NAVWORLD/GAME may be higher ROI.

## Recommendation
Option 3 for Phase 2 (accept 347, focus on NAVWORLD/GAME). Revisit L2 in Phase 3 if LIVEWEB becomes the differentiator.

Awaiting your decision.
