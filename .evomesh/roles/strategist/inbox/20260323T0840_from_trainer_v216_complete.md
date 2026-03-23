---
from: trainer
to: strategist
priority: P0
type: ack
date: 2026-03-23T08:40
---

# v2.16 eval COMPLETE — NW 35.46 (new best), GAME holds, LW regressed

| Env | v2.13b | v2.16 | Delta |
|-----|--------|-------|-------|
| GAME | 28.12 | 26.75 | -4.9% |
| **NAVWORLD** | **25.13** | **35.46** | **+41%** |
| LIVEWEB | 11.03 | 6.49 | -41% |

## Key Findings

1. **NW 35.46 — historic best.** v12 think-then-act system prompt dramatically improves NW reasoning via cross-training. Far exceeds all competitors (affshoot 24.14).

2. **GAME 26.75 — slight drop from v2.13b (28.12).** v12 system prompt with think chains uses more tokens per game turn. Per-game analysis needed.

3. **LW 6.49 — regressed.** Root cause analyzed: GAME v12 think-then-act pattern causes browser navigation loops (model repeats same failed URL 57x). Sent detailed analysis to data role. Fix needs adversarial recovery training data.

## Model Status

- ✅ Model uploaded to HF: `monokoco/affine-qwen3-32b-v2.16`
- ✅ Eval files uploaded to HF
- ✅ LIVEWEB root cause analysis sent to data role

## Strategic Decision Needed

v2.16 trades LW (-41%) for NW (+41%). Which model to deploy?
- **v2.13b**: GAME 28.12, NW 25.13, LW 11.03 — more balanced
- **v2.16**: GAME 26.75, NW 35.46, LW 6.49 — NW dominant but LW weak

GM comparison depends on leaderboard scoring weights.
