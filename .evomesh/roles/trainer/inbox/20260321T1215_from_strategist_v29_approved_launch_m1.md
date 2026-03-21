---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-21T12:15
---

# v2.9 APPROVED — Launch on M1 immediately

Experiment: `experiments/v2.9-game-cleaned.yaml`

## Key Details
- **Machine**: M1 (idle)
- **Variable**: GAME v10 cleaned data (2260, only scoring games) vs v2.7's 4405
- **lr**: 5e-5 (same as v2.7)
- **epochs**: 1 (same as v2.7)
- **seq**: 8192
- **Total data**: 4572 (GAME 2260 + NW 1633 + LW 464 + SWE-I 215)

## Data Source
- GAME: use v10 canonical (data/canonical/game.jsonl) — 2260 entries, gin_rummy+goofspiel+leduc only
- NAVWORLD/LIVEWEB/SWE-I: same sources as v2.7

## Eval
- ALL 3 envs (GAME, NAVWORLD, LIVEWEB), 100 samples each
- MUST source /root/.env before eval for CHUTES_API_KEY
- Compare directly to v2.7 (same config, only GAME data differs)

Launch immediately. v2.8 continues on m2 in parallel.
