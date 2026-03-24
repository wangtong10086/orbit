# Data-Game TODO

## Canonical: v6 (restored) — 9088 entries

| Game | Count | Bot | Think Format |
|------|-------|-----|-------------|
| goofspiel | 1048 | Rule v4 | Rule think (hand/prize/bid) |
| leduc_poker | 1069 | Rule v4 | Rule think (pot odds/range) |
| liars_dice | 1829 | MCTS 10000sim | MCTS stats T1 + Rule fallback T2+ |
| gin_rummy | 1026 | MCTS 2000sim | MCTS stats (draw/discard/knock) |
| othello | 1358 | MCTS 3000sim | MCTS stats + corner/edge context |
| hex | 1211 | MCTS 3000sim | MCTS stats + bridge context |
| clobber | 1547 | MCTS 5000sim | MCTS stats + safe capture context |

## Experiment History

### v2.20 (v6 data, 9088 entries) — GAME best = 28.2%
- gin_rummy 53.9% (best ever, +8% from MCTS data)
- goofspiel 86.7%, leduc 54.7%
- liars_dice 0% (regression from v2.17b's 20%)
- spatial games 0%
- Model 0% think rate

### v2.21 (v7 data, 8259 entries) — FAILED = 24.9%
- v7 changes: system prompt aligned to eval + liars_dice resampled 1829→1000
- Result: all games worse. gin_rummy 42.6% (-11), goofspiel 80% (-7)
- Model still 0% think (token counts identical to v2.20)
- **Root cause**: data reduction (9088→8259) hurt action quality; think alignment ineffective
- **Rolled back to v6**

## Key Learnings
1. Model does NOT think in eval — confirmed across v2.17a/b, v2.20, v2.21
2. `strip_think_tags=True` strips before recording → can't see think in JSON, but token counts prove no think
3. 1 epoch SFT cannot override base model's instruction-following ("only output number")
4. Data quantity matters — removing 829 entries caused measurable regression
5. Think chains still useful as "training padding" — model learns action patterns from the full sequence

## Next Steps
- [ ] Accept model won't think; optimize purely for action quality
- [ ] v2.20 (v6) is current GAME best — use as baseline
- [ ] liars_dice fix: need approach that doesn't reduce total data count
