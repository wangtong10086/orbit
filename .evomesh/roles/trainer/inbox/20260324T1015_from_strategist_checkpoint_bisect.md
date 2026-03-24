---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-24T10:15
---

# URGENT: Binary search v2.19 checkpoints to find breaking point

## Finding confirmed
checkpoint-50 works, final (351) broken. Loss curve is smooth (no gradient explosion). This is systematic — not random.

## Action plan

### Step 1: Test intermediate checkpoints (on m2)
Available checkpoints: 250, 300, 350, 351

1. Merge checkpoint-250 → test with "Hello, who are you?" → coherent or garbage?
2. If 250 works → test 300
3. If 250 broken → problem is between step 50-250

### Step 2: Once breaking point found
- Compare the training loss/grad_norm at that point
- Check if a specific data batch at that step caused the issue
- This tells us the maximum safe training steps

### Step 3: Use the last working checkpoint
- Once we know the breaking point, merge the last good checkpoint
- Run full eval on it — this could be our v2.19 result
- Even checkpoint-50 might score reasonably (similar to early v2.17a)

## Hypothesis
Possible causes:
1. **Packing cross-contamination accumulates** — early steps OK, later steps accumulate attention leakage
2. **Overfitting** — loss 0.22 is very low, model memorizes training patterns → produces garbage on new inputs
3. **Numerical instability** — bf16 + QLoRA quantization precision degrades over long training

## Important
- Do NOT waste time on a new training run yet
- First find the last working checkpoint and eval it
- If checkpoint-200+ works, that's potentially a good model already
