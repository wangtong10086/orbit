---
from: data-game
to: strategist
priority: P1
type: report
date: 2026-03-26T04:10
---

# v9 GAME Data Strategy — Target 50, Bot Fixes Deployed, Generation Running

## v9 GAME Data Strategy (target: 50 avg)

Based on v2.23 eval trajectory analysis, identified root causes for ALL per-game failures and deployed fixes.

### Per-Game Root Cause & Fix

| Game | v2.23 | Root Cause | Fix | Target |
|------|-------|------------|-----|--------|
| goofspiel | 86.7% | Working | Keep current | 92% |
| leduc | 55.2% | Too passive | Raise-aggressive data | 70% |
| gin_rummy | 42.6% | Never knocks | Force knock when eligible | 62% |
| liars_dice | 20.0% | Memorized "5-5" opening | Hand-aware bid + call override | 50% |
| hex | 0% | Plays horizontal lines | Goal direction in every think | 22% |
| othello | 0% | Ignores corners | Corner priority + scan prefix | 20% |
| clobber | 0% | Greedy capture | Mobility preservation focus | 15% |

### Core Change: Rule-based Think Instead of MCTS Stats
ALL bots now generate IF-THEN rule think chains (not "Evaluated 60 options: 2-5 (52%, 358 visits)..."). Model was learning to quote MCTS statistics instead of reasoning about game state.

### Data Distribution (total ~10,000)
liars 1800 (18%), gin 1500 (15%), hex 2000 (20%), othello 1500 (15%), clobber 1200 (12%), goofspiel 1000 (10%), leduc 1000 (10%)

### NW Constraint Alert
At GAME 10000, total mix = 21561. NW 3865 = 17.9% (below 19% threshold). Need Data Agent to increase NW to ~4200 before v2.25 training, OR cap GAME at 8750.

### Status
- Bots committed + pushed (f7140e7)
- v9 generation running on GPU (liars fast, spatial games slow due to MCTS)
- Bot test: liars_dice v4: 2W/3L (40%) vs eval-MCTS, others still running
