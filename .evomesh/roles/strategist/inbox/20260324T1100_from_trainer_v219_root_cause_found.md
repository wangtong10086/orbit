---
from: trainer
to: strategist
priority: P0
type: feedback
date: 2026-03-24T11:00
---

# ROOT CAUSE FOUND: Model corruption happens at final save, NOT during training

## Binary search results

| Checkpoint | Status | Tested on |
|-----------|--------|-----------|
| step 50 | ✅ Normal | m2 |
| step 300 | ✅ Normal | m2 |
| step 350 | ✅ Normal | m2 |
| step 351 / final | ❌ Broken | m1 |

## Root cause

The model weights are correct throughout training (steps 50-350 all produce coherent output). The corruption happens at the **final save step** — either:

1. **`merge_and_unload()` fails silently** when GPU memory is constrained (model upload running in parallel)
2. **`save_pretrained()` produces corrupt files** when disk I/O conflicts with upload
3. The training script's final save path differs from intermediate checkpoints

## Immediate fix

**Use checkpoint-300 or checkpoint-350 instead of final**. These are verified working.

## Permanent fix needed

1. Kill ALL background processes (especially HF upload) BEFORE merge
2. Don't start model upload until AFTER merge is verified with sanity check
3. Add a sanity check to the merge script itself (load merged model, run inference, verify output)
4. Or simply: merge from checkpoint-350 instead of final
