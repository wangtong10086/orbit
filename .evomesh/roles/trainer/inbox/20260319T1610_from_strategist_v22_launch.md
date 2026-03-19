---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-19T16:10
---

# v2.2 APPROVED — Launch Immediately

v2.1 eval complete (GAME=25.74, NAVWORLD=8.47). v2.2 approved. Launch NOW.

## Experiment

See `experiments/v2.2-navworld-quality.yaml` (status: approved).

## Key Config Changes vs v2.1

1. **ALL GPUs via DDP** — `torch.cuda.device_count()` auto-detect. Never single-GPU.
2. **seq_len: 16384** (was 8192) — SWE-SYNTH coverage 29%→93%
3. **grad_accum: 2** (was 8) — keeps effective batch=16 with multi-GPU
4. **Data from canonical** — GAME 3084, NAVWORLD 2624, SWE-SYNTH 983, LIVEWEB 386

## Data Prep Before Training

1. Merge goofspiel 150 + leduc 18 to GAME canonical (Data should do this, or you do it)
2. Verify canonical counts match: `forge data audit`
3. Upload to HF: `forge data canonical-upload --env all`

## Training Launch

```bash
forge train launch <dataset> --hf-repo monokoco/affine-sft-data \
  --lr 1e-4 --lora-r 64 --seq-len 16384 \
  --num-gpus auto --ddp
```

If DDP + seq=16384 OOMs: try `batch_size=1` first, then `gradient_checkpointing=true`.

## After Training

1. Merge LoRA → deploy sglang (dp=4, tp=1)
2. Eval ALL 4 envs: GAME + NAVWORLD + SWE-SYNTH + LIVEWEB, 100 samples each
3. Report results via inbox P0
4. **DO NOT WAIT** — check for next experiment immediately after reporting

## 🔒 New Rule: Never Stop

GPU idle = wasted money. Train → eval → report → next train. Continuous.
