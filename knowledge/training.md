# Training Knowledge

## Key Facts
- Base model: Qwen/Qwen3-32B (always train from base, not from other fine-tunes)
- Pre-quantized: unsloth/Qwen3-32B-bnb-4bit (18GB vs 65GB, ~90s download)
- Method: QLoRA (4-bit NF4)
- Training from top model (#2) failed: loss oscillated wildly (0.6→0.9), QLoRA cannot stably learn on deeply-tuned models
- SFT 1 epoch is sufficient; 2+ epochs risk overfitting on small datasets

## Hyperparameter Evolution

| Param | v1-v3 | v4 | v5 | v6 | v7-v10 (current best) |
|-------|-------|-----|-----|-----|----------------------|
| lr | 2e-5 / 1e-5 | 1e-4 | 1e-4 | 5e-5 | **1e-4** |
| LoRA r | 16 / 32 | 64 | 128 | 64 | **64** |
| LoRA alpha | 32 / 64 | 128 | 256 | 128 | **128** |
| epochs | 3 / 2 | 1 | 1 | 1 | **1** |
| max_seq_len | 4096/8192 | 4096 | 4096 | 4096 | **4096** |
| batch | 2/1 | 2 | 2 | 2 | **2** |
| grad_accum | 8/16 | 4 | 4 | 8 | **8** |
| packing | False | True | True | True | **True** |
| warmup | 10% | 3% | 3% | 3% | **3%** |
| max_grad_norm | 1.0 | 0.3 | 0.3 | 0.3 | **0.3** |

## Key Findings

### Learning Rate
- 1e-5 was 10x too low for QLoRA (v1-v3), loss plateaued at ~0.45
- 1e-4 is the QLoRA standard range, loss reaches ~0.11-0.18
- 5e-5 (v6) was a regression, reverted to 1e-4 in v7

### LoRA Rank
- r=16: insufficient for multi-environment (v1-v3)
- r=64: good balance of capacity and memory (v7+)
- r=128 (v5): marginal benefit, more memory, not clearly better

### Packing
- Short samples (GAME replies are 1-3 chars) benefit enormously from packing
- 2-3x training efficiency improvement
- Must be False if OOM (Targon single GPU needed batch=1, seq=2048, no packing)

### Epochs
- 1 epoch sufficient for 5000-15000 samples
- 3 epochs on 4528 samples caused catastrophic forgetting risk
- SFT best practice: 1-2 epochs max

## Loss Convergence Patterns
- Initial loss: ~0.67-0.86 (step 10)
- Rapid drop: to ~0.3 by step 50
- Plateau: ~0.11-0.20 depending on data mix
- v8 (focused 4 envs): 0.11 final loss
- v9 (6 envs): 0.14 final loss
- v10 (7 envs): 0.19 final loss
- More environments = higher final loss (expected, more diverse)

## Training Speed
- 4x H200 DDP: ~46s/step at seq=4096, packing=True
- Single H200: ~38-52s/step at seq=2048
- Typical run: 230-440 steps, 3-9 hours

## Data Mix Ratios (v10 current)
| Env | Entries | Share |
|-----|---------|-------|
| GAME | 4610 | 34.7% |
| LGC-v2 | 3353 | 25.2% |
| PRINT | 2899 | 21.8% |
| SWE-SYNTH | 1350 | 10.2% |
| NAVWORLD | 633 | 4.8% |
| LIVEWEB | 437 | 3.3% |

## DPO Pipeline (Built, Not Yet Deployed)
- 2688 preference pairs extracted from DDB (multi-miner same task)
- beta=0.1, lr=5e-6, batch=1, grad_accum=8
- Plan: SFT checkpoint → DPO alignment
- Not yet run due to infrastructure constraints

## Current Best / Status
- v10 is latest deployed model (7 envs, 13733 entries, loss ~0.19)
- v11 in training (NAVWORLD 2154 entries, total 15273)

## Improvement Directions
- DPO on top of SFT checkpoint
- Per-environment specialist models merged via weight averaging
- Curriculum learning (easy→hard games)
- Higher data quality over quantity (geometric mean penalizes weak envs)
