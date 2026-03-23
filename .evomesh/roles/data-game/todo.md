# Data-Game TODO

## Bot Strategy Status (2026-03-23)

All 7 games have rule-based think chains + MCTS action selection.

| Game | Bot | Think Rules | Test | Status |
|------|-----|-------------|------|--------|
| goofspiel | Rule v4 | hand→prize→bid/conserve→score diff | 95% | ✅ Ready |
| leduc_poker | Rule v4 | hand→pot odds→opponent range | 60% | ✅ Ready |
| liars_dice | MCTS v3 | Step1→Step2→Step3 framework | 80% 8/10 | ✅ Ready |
| gin_rummy | MCTS v2 | deadwood→meld→knock timing | 80% 8/10 | ✅ Ready |
| othello | MCTS v5 | 9 rules (corner/chain/X-sq/compact/parity) | 67% 2/3 | ⏳ Stable chain fix验证中 |
| hex | MCTS v8b | bridge/chain/double threat/acute corner | ⏳ 10局测试中 | ⏳ 验证中 |
| clobber | MCTS v5 | safe capture/fragment/chain/mobility/parity | 100% 3/3 | ✅ Ready |

## Pending Verification
- [ ] hex v8b 10-game test (all board sizes 5/7/9/11)
- [ ] othello v5 fixed sample — verify stable chain count correct
- [ ] clobber v5 retest with fixed chain detection

## Next: Full Re-generation
After all strategies verified:
1. Delete ALL old canonical data
2. Regenerate all 7 games with v12 system prompt (think-encouraging)
3. Use latest bot versions (v3-v8b)
4. Upload to canonical + HF

## Critical Fixes Applied
- System prompt: "respond ONLY action ID" → "think in `<think>` tags then action ID"
- othello: stable chain only triggers when action genuinely extends chain
- clobber: chain awareness only for real threats (≥3), not normal adjacency
- liars_dice: fixed decision framework (Step1→Step2→Step3)
