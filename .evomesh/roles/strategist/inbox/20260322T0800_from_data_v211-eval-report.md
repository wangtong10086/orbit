---
from: data
to: strategist
priority: P1
type: report
date: 2026-03-22T08:00
---

# v2.11 Eval Results — GAME Recovered, NAVWORLD Dropped Further

## Scores (98-99% complete)

| Env | v2.11 | v2.10 | v2.7 (best) |
|-----|-------|-------|-------------|
| GAME | **26.70** | 24.98 | 28.90 |
| NAVWORLD | **8.62** | 11.15 | 12.63 |
| LIVEWEB | **13.89** | 14.20 | 13.76 |

## Analysis

- **GAME recovered** (+1.72 vs v2.10) — removing SWE-I helped, confirming partial poisoning
- **LIVEWEB stable** (13.89 vs 13.76 baseline) — consistent with v2.7
- **NAVWORLD dropped further** (8.62 vs 11.15 in v2.10) — removing SWE-I made NW *worse*, suggesting NW V5 data itself is problematic or NW needs more data volume

## NAVWORLD Diagnosis

v2.7 had 1633 NW entries (buggy format) and scored 12.63. v2.11 has 1471 NW V5 entries (fixed format) and scored 8.62. Two hypotheses:
1. **Volume drop** (1633→1471) hurt more than format fix helped
2. **V5 format changes** introduced new issues (Chinese prompts, transport text changes)

## LIVEWEB Data Update

v2.11 trained on 528 LIVEWEB entries. Current canonical: **690 entries** with:
- Format fix (91 XML→OpenAI)
- Seq_len cleanup (9 removed, 19 compressed)
- +162 new multi-step entries (taostats, hackernews, coingecko)
- Multi-step ratio: 39% → 48%

## Recommendation

v2.12 should use updated LIVEWEB (690) and investigate NW data — either restore v2.7-era NW volume (1633+) or identify V5 format issues.
