# Data-Game TODO

## v12 Data Generation — READY FOR TRAINING

**Canonical: 5584 entries, HF synced. All v12 system prompt.**

| Game | Count | Bot | Think Rules | Status |
|------|-------|-----|-------------|--------|
| goofspiel | 1048 | Rule v4 | hand→prize→bid/conserve→score-diff | ✅ |
| leduc_poker | 1087 | Rule v4 | pot odds→opponent range→call/raise/fold | ✅ |
| liars_dice | 1199 | MCTS v3 10000sim | Step1→Step2→Step3 decision framework | ✅ |
| clobber | 1528 | MCTS v5 5000sim | safe capture/fragment/chain/mobility/parity | ✅ |
| gin_rummy | 258 | MCTS v2 2000sim | deadwood/meld/knock timing | 🔄 growing |
| othello | 239 | MCTS v5 3000sim | 9 rules (corner/chain/X-sq/compact/parity) | 🔄 growing |
| hex | 225 | MCTS v8b 3000sim | bridge/chain/double-threat/acute-corner | 🔄 growing |

## Key Fixes vs v2.13b (which scored 0 on 4 games)
1. System prompt: "Do NOT include" → "think in `<think>` tags" (CRITICAL)
2. Think content: vague descriptions → IF-THEN rule patterns
3. Othello: corner/stable-chain/X-square/compact/parity rules
4. Hex: bridge pattern (unbreakable virtual connection)
5. Clobber: safe capture/fragment/chain awareness
6. Liars_dice: fixed Step1→Step2→Step3 decision framework
7. generate_fast.py: system prompt replacement in generator

## Awaiting
- Training with v12 data → eval to verify 0-score games improve
- gin/oth/hex continue growing in background
