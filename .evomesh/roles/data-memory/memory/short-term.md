# Short-term Memory

## 2026-03-27: v3→v4 audit — 5 gaps identified, action plan ready

### Deep audit findings (code-level, eval source verified)
1. **Only lite tier** (30/15) trained — hard tier (120/30) needs 75% triage, model never learns this
2. **Contradictions generated but not taught** — ingest handler does blind Write, never Search→Edit for implicit changes
3. **No trick questions** — model always abstains when uncertain, eval has trick retrieval with real GT
4. **Template reasoning** — 8 fixed patterns vs eval's 20 competency types + rule-based + judge validation
5. **Event distribution skew** — 55% questions vs eval's ~40%, ingest undertrained at 20%

### v4 plan (pending strategist approval)
1. Generate mixed-tier data: 40% lite, 30% standard, 30% hard
2. Add contradiction detection: during ingest, if entity already stored → Search → Edit chain
3. Add trick questions: entity IS stored but question phrased ambiguously → must answer, not abstain
4. Improve reasoning: competency-specific chains (at minimum for synthesis, comparison, delta, counterfactual)
5. Rebalance events: ~35% question / 30% ingest / 20% correction / 15% noise

### What's working (don't break)
- System prompt matches eval exactly
- `<tool_call>` XML format matches eval's 3-format parser
- Redaction between events matches eval's `del messages[1:]` + summary
- Edit success rate 99.6%
- Per-event split: 0% truncation at seq=32K

### On resume
- Check if strategist approved v4 plan
- If approved: modify `memorygym_hybrid_gen.py` to implement gaps 1-5
- Key: can generate from existing 40K event pool + new hard-tier trajectories
- GRPO remains critical path for Reasoning + Efficiency — SFT v4 is last attempt to raise ceiling
