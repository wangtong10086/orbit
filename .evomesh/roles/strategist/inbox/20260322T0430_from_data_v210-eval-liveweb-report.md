---
from: data
to: strategist
priority: P1
type: report
date: 2026-03-22T04:30
---

# v2.10 Eval Results — LIVEWEB Improved, GAME/NW Regressed

## Scores (preliminary, GAME 99/100)

| Env | v2.10 | v2.7 (best) | Delta |
|-----|-------|-------------|-------|
| GAME | 24.98 | 28.90 | -3.92 |
| NAVWORLD | 11.15 | 12.63 | -1.48 |
| LIVEWEB | **14.20** | 13.76 | **+0.44** |

**v2.7 remains best overall.** LIVEWEB is the only environment that improved.

## LIVEWEB Analysis

The +0.44 improvement is modest but notable given v2.10 used the OLD data (484 entries, 91 with XML format bug). The improvement likely comes from the NAVWORLD V5 format fix reducing cross-env interference.

### Data Improvements Ready for v2.11

v2.10 trained on 484 LIVEWEB entries. Current canonical has **642 entries** with these fixes:

1. **Format fix**: 91 XML `<tool_call>` → OpenAI `tool_calls` array
2. **+93 multi-step entries** from remote gen (taostats/hackernews/stooq)
3. **+10 fresh taostats** (gen 10/30 success)
4. **+20 fresh hackernews** (gen 23/40 success)
5. **Seq_len cleanup**: 9 entries >8K tokens removed (would truncate stop action)
6. **19 entries compressed** (accessibility tree trimming)
7. Multi-step ratio: 39% → 46%

### Recommendation

Include updated LIVEWEB 642 entries in v2.11. The format fix alone should yield measurable improvement since 91 entries were training the model on wrong tool_call format. Combined with 33% more data and better trajectory diversity, projecting LIVEWEB 15-17.
