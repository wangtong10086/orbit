---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-23T03:47
---

# v2.16 APPROVED — GAME v12 system prompt fix. Launch IMMEDIATELY.

## v2.15 is BROKEN (same root cause as v2.13)

NW 100/100 ALL ZEROS. GAME/LW 0 scored after 52 min. The old system prompt
("respond with ONLY the action ID") kills model reasoning across ALL envs.

**Kill v2.15 eval immediately** — results are worthless.

## Root Cause (from data-game)

Training data system prompt said "Do NOT include descriptions or explanations."
This made the model suppress all thinking. 0/1157 outputs had think blocks.

**v12 fix**: System prompt now says "First, think through your strategy step by
step inside <think> tags. Then, output ONLY the action ID."

## v2.16 Data Mix — ALL canonical, no subsampling

| Env | Count | Source |
|-----|-------|--------|
| GAME | **ALL v12** (6511) | canonical — VERIFY v12 system prompt is in place |
| NAVWORLD | **ALL** (~1700) | V5 canonical |
| LIVEWEB | **ALL** (~1055) | latest canonical |
| SWE-I | **0** | excluded |
| **Total** | **~9266** | |

## CRITICAL: Verify GAME data has v12 system prompt

Before training, run:
```bash
head -1 data/canonical/game.jsonl | python3 -c "import json,sys; d=json.loads(sys.stdin.readline()); print(d['messages'][0]['content'][:200])"
```

Must see "think through your strategy" — NOT "respond with ONLY the action ID".
If it shows old prompt, download v12 from HF: `forge data canonical-download --env GAME`

## Config

Same as always: lr=5e-5, seq=8192, epochs=1, batch=2, grad_accum=2.

## After Eval: FULL analysis per ROLE rules

Per-game GAME breakdown (which of 7 games score? do they have think blocks?),
NW tool call analysis, LW per-plugin analysis.

## AMAP Keys

Ensure both `export AMAP_MAPS_API_KEY` and `export AMAP_API_KEY` are in .env.
