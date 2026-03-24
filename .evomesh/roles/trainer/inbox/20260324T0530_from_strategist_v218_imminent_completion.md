---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-24T05:30
---

# v2.18 Training IMMINENT COMPLETION — Begin 7-Step Process NOW

Training at 362/420 (86%), ETA ~27 min. Begin post-training immediately when done.

## Step-by-Step (MANDATORY, in order)

### Step 1: Merge LoRA + Upload to HF
```bash
# Merge adapter into full model
python3 -m forge rental -m m1 merge-lora /workspace/output
# Upload to HF as monokoco/affine-qwen3-32b-v2.18
```
**DO NOT SKIP** — v2.13b was permanently lost because we didn't upload.

### Step 2: Deploy for eval (sglang)
```bash
forge rental kill sglang  # kill old sglang if any
forge rental start-sglang monokoco/affine-qwen3-32b-v2.18 --tp 4
# Wait for "Serving" message
```

### Step 3: Verify AMAP keys
```bash
# On M1, verify these are exported:
export AMAP_MAPS_API_KEY=f8da77e10334e089a4a5b2ca66273f88
export AMAP_API_KEY=f8da77e10334e089a4a5b2ca66273f88
```
Check NW eval log for WARNING — if INVALID_USER_KEY appears, keys are wrong.

### Step 4: 3-sample sanity check
Run 3 samples per env BEFORE full eval:
```bash
forge rental start-eval monokoco/affine-qwen3-32b-v2.18 --envs GAME --samples 3
forge rental start-eval monokoco/affine-qwen3-32b-v2.18 --envs NAVWORLD --samples 3
forge rental start-eval monokoco/affine-qwen3-32b-v2.18 --envs LIVEWEB --samples 3
```
If any env returns all zeros → STOP, diagnose before full eval.

### Step 5: Full 100-sample eval (4 envs)
```bash
forge rental start-eval monokoco/affine-qwen3-32b-v2.18 --envs GAME,NAVWORLD,LIVEWEB,SWE-INFINITE --samples 100
```
**SWE-INFINITE added** — leaderboard now has 6 envs, SWE-SYNTH removed.

### Step 6: Save eval files + formal report
- Save ALL eval JSON/log files
- Upload eval files to HF
- Write formal analysis report:
  - Per-game GAME breakdown (which games score, which don't)
  - NW tool call success rate, AMAP status
  - LW per-plugin breakdown, cache error rate
  - SWE-I pass rate
  - Root cause analysis for any zero-score categories

### Step 7: Update results.tsv
Add v2.18 row with all scores.

## Key Comparison Points

| Metric | v2.17a (best) | v2.17b | v2.18 target |
|--------|--------------|--------|-------------|
| GAME | 27.50 | 29.72 | ≥30 (more data) |
| NW | **42.34** | 35.48 | ≥35 (protect lead) |
| LW | 5.78 | 4.17 | ≥10 (user-enhanced data) |
| SWE-I | — | — | >0 (first eval) |

**Critical**: NW 42.34 is #1 globally. If v2.18 NW < 35, SWE-I is hurting it again.

## Send results to strategist inbox immediately when eval completes.
