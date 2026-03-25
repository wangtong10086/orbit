# Data-Game TODO

## Canonical: v8 — 9088 entries, eval-aligned prompt

System prompt matches eval exactly: "You must respond with ONLY the action ID. Do NOT include descriptions."
Assistant responses retain `<think>` blocks. Model must learn to think despite instruction.

| Game | Count | % | Bot | Think |
|------|-------|---|-----|-------|
| goofspiel | 1048 | 12% | Rule v4 | Rule (hand/prize/bid) |
| leduc_poker | 1069 | 12% | Rule v4 | Rule (pot odds/range) |
| liars_dice | 1829 | 20% | MCTS 10000sim | MCTS T1 + Rule T2+ |
| gin_rummy | 1026 | 11% | MCTS 2000sim | MCTS (draw/discard/knock) |
| othello | 1358 | 15% | MCTS 3000sim | MCTS + corner/edge |
| hex | 1211 | 13% | MCTS 3000sim | MCTS + bridge/chain |
| clobber | 1547 | 17% | MCTS 5000sim | MCTS + safe capture |

## Code Alignment ✅
- `generate_fast.py`: uses eval-format prompt (v12 reverse-replacement removed)
- `base_agent.py` (affinetes): same eval-format prompt
- Data and code fully aligned

## Experiment History

| Version | Data | GAME | Key Finding |
|---------|------|------|-------------|
| v2.17b | 5584 (v6 prompt) | 29.7% | liars_dice 20% (best), no think |
| v2.20 | 9088 (v6 prompt) | 28.2% | gin_rummy 53.9% (best), no think |
| v2.21 | 8259 (eval prompt) | 24.9% | data reduction hurt, no think |
| v2.21+thinking | 8259 (eval prompt) | ~15% | sglang reasoning_parser=qwen3 eval, partial think but buggy |
| v2.22 | 9088 (v6 prompt) | pending | v6 restored + NW 2966 |

## Key Findings

### Why model doesn't think
- Qwen3 chat template has `enable_thinking` flag
- sglang `--reasoning-parser qwen3` enables thinking mode
- BUT: eval system prompt "Do NOT include descriptions" suppresses think output
- Model with v6 prompt ("think in `<think>` tags") DOES think — confirmed by direct API test
- 1 epoch SFT insufficient to override base model instruction-following

### Thinking is the key to unlocking 0-score games
- 4 games at 0% (liars_dice/hex/othello/clobber) = max possible without them is 43%
- Must get these scoring to reach 50+
- With thinking enabled, model produces high-quality strategy reasoning
- Without thinking, only pattern matching → insufficient for spatial games

### Eval deployment requirement
- sglang MUST use `--reasoning-parser qwen3`
- eval `strip_think_tags=True` handles `<think>` in content automatically
- No eval code changes needed

## Next Steps
- [ ] v2.22 training in progress (v6 prompt data + NW 2966)
- [ ] After v2.22: re-eval with reasoning_parser=qwen3 to test thinking
- [ ] v8 data ready for next training (eval-aligned prompt, full 9088)
