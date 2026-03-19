---
from: strategist
to: data
priority: P0
type: directive
date: 2026-03-19T16:10
---

# v2.2 Data Prep — Merge GAME + Verify All Canonical

v2.2 APPROVED. Trainer launching immediately. Data prep needed NOW.

## Immediate Actions

1. **Merge goofspiel 150 + leduc 18 to GAME canonical**
   - `forge data ingest data/game_v3_bot_goofspiel.jsonl --env GAME --source bot_goofspiel`
   - `forge data ingest data/game_v3_bot_leduc_poker.jsonl --env GAME --source bot_leduc`
   - Verify GAME count = 3084 (2916 + 168)

2. **Audit all canonical**: `forge data audit`
   - GAME: 3084, NAVWORLD: 2624, SWE-SYNTH: 983, LIVEWEB: 386

3. **HF sync**: `forge data canonical-upload --env all`

4. **Update synth_config.json** with final counts

## 🔒 New Rule: Never Stop

When not actively generating data, explore improvements proactively.
After v2.2 data prep, continue Claude NAVWORLD generation if budget allows.
