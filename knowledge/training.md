# Training Knowledge

## Key Facts
- Base model: Qwen/Qwen3-32B (always train from base, not from other fine-tunes)
- Pre-quantized: unsloth/Qwen3-32B-bnb-4bit (18GB vs 65GB, ~90s download)
- Method: QLoRA (4-bit NF4)
- Training from top model (#2) failed: loss oscillated wildly (0.6→0.9), QLoRA cannot stably learn on deeply-tuned models
- SFT 1 epoch is sufficient; 2+ epochs risk overfitting on small datasets

## Current Best Config (v7-v12)

| Param | Value | Notes |
|-------|-------|-------|
| lr | **1e-4** | 1e-5 too low (v1-v3 plateau), 5e-5 regressed (v6) |
| LoRA r | **64** | r=16 insufficient, r=128 marginal benefit |
| LoRA alpha | **128** | 2x rank |
| epochs | **1** | 3 epochs on 4528 samples → catastrophic forgetting |
| seq_len | **8192** | SWE-SYNTH needs it; GAME unaffected (v12 confirmed) |
| batch | **2** | |
| grad_accum | **8** | effective batch 16 |
| packing | **True** | 2-3x efficiency; Unsloth latest fixes cross-sequence contamination |
| warmup | **3%** | |
| max_grad_norm | **0.3** | |

## Loss Convergence
- Initial: ~0.67-0.86 (step 10)
- Rapid drop: ~0.3 by step 50
- Plateau: 0.11-0.20 (more envs → higher final loss)
- Abnormal: >0.5 after step 50 → terminate immediately
- v8 (4 envs): 0.11 | v9 (6 envs): 0.14 | v10 (7 envs): 0.19

## Sequence Length
- seq=4096: default, works for GAME/NAVWORLD/LIVEWEB
- seq=8192: needed for SWE-SYNTH (98% truncated at 4096 → 37% at 8192)
- v12 confirmed: seq=8192 works, GAME score unaffected
- Trade-offs: ~80s/step (vs ~48s), loss ~0.21 (vs ~0.17), ~82GB VRAM

## Training Speed
- Single H200 at seq=8192: ~88-92s/step
- 4x H200 DDP at seq=4096: ~46s/step
- Typical run: 230-440 steps, 6-14 hours at seq=8192

## Historical Best (old repo, for reference)
- v10: 7 envs, 13733 entries, loss ~0.19, GAME=22.0, NAVWORLD=5.1
- v11: 7 envs, 15273 entries, loss ~0.17, GAME=22.6, NAVWORLD=5.7
- v12: 7 envs, 15367 entries, seq=8192, loss ~0.21, GAME=22.0 (partial eval)
- Total old repo cost: ~$200

## Packing Safety
- Latest Unsloth fixes cross-sequence contamination via position IDs
- Supports FA2, FA3, xFormers, SDPA backends
- v1/v2 FA2 warnings may be from older Unsloth; safe with latest version

## Tool Calling (NAVWORLD critical)
- Training: `tokenizer.apply_chat_template(messages, tools=tools)` → Qwen3 native format
- Inference: sglang with `--tool-call-parser qwen25`
- Both required — without either, NAVWORLD scores 0
- v8 breakthrough: 0% → 33% non-zero when both fixes applied
- Risk: `qwen25` parser may be unreliable for Qwen3 (sglang #7769). Fallback: `hermes`

## DPO Pipeline (built, unused)
- 2688 preference pairs: GAME 589, LGC-v2 800, NAVWORLD 241, PRINT 800, SWE-SYNTH 258
- Config: beta=0.1, lr=5e-6, batch=1, grad_accum=8
- CLI: `forge train dpo-launch`

## Phase 3+ Methods (research, 2026-03-18)

### Method Selection
| Env | Recommended | Rationale | Fallback |
|-----|------------|-----------|----------|
| GAME | **GRPO** | Win/loss = verifiable reward; DeepResearch/QwQ/DeepSeek-R1 all chose GRPO | DPO (589 pairs) |
| NAVWORLD | **GRPO** | Tool-call correctness = verifiable reward | DPO (241 pairs) |
| SWE-SYNTH | **RLVR** | Binary pass/fail = natural verifiable reward | DAPO (long seq stability) |
| LIVEWEB | Hold | Data too long, needs upstream compression | — |

### GRPO (Group Relative Policy Optimization) — preferred
- Eliminates critic model; samples multiple responses, normalizes reward within group
- Stronger than DPO: generates new responses during training (not limited to static pairs)
- Industry consensus: DeepResearch + QwQ + DeepSeek-R1 all chose GRPO

### RLVR (Reinforcement Learning with Verifiable Rewards)
- Auto-verification (unit tests, math checks) replaces human preference labels
- Perfect match for SWE-SYNTH binary scoring
- DeepSeek-R1 proved pure RLVR can produce emergent reasoning

### Key Insights from DeepResearch
- "Data/environment stability matters more than RL algorithm choice"
- Rejection sampling: generate many trajectories, keep only high-quality diverse ones
- Dynamic difficulty filtering: drop tasks model always passes/fails, keep medium difficulty
- Pure 0/1 reward works (no format reward needed)
- Action-level penalties prevent reward hacking (e.g. penalize "no action" or "invalid tool call")

### SFT Plateau Triggers (when to switch methods)
- 2x data yields <15% improvement → DPO/GRPO
- Structural zero: 0% across 3+ versions → SFT-unlearnable, try RL or drop
- Rank stagnation for 3+ versions → method change required
