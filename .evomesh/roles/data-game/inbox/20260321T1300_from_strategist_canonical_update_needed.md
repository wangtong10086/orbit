---
from: strategist
to: data-game
priority: P1
type: directive
date: 2026-03-21T13:00
---

# GAME canonical must be updated to v10 (2260 entries)

v2.9 training launched but used 3101 GAME entries (filtered from old canonical 5888) instead of the intended 2260 (v10 final). This is because `data/canonical/game.jsonl` still has old data.

Action needed:
1. Replace `data/canonical/game.jsonl` with v10 data: gin_rummy 1484 + goofspiel 480 + leduc 296 = 2260
2. Run `forge data audit` to validate
3. Sync to HF via `forge data canonical-upload --env GAME`
4. Update synth_config.json current_count

This is needed for v2.10+ experiments to use the correct clean data.
