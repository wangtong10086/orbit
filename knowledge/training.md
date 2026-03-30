# Training Knowledge

## Method: Full Fine-Tuning (v2.28+)

- Base model: Qwen/Qwen3-32B (32.8B params, 100% trainable)
- Framework: ms-swift 4.0.2 + DeepSpeed ZeRO-3
- Machine: 8x H200 (m3), seq=32768, bf16
- QLoRA (v2.1-v2.25) archived — Full FT gave +35% GAME, +60% LW improvement

## Current Config (v2.28)

| Param | Value | Notes |
|-------|-------|-------|
| method | Full SFT | NOT QLoRA |
| framework | ms-swift 4.0.2 | Handles chat template, tool_calls, loss masking |
| deepspeed | ZeRO-3 + CPU offload | ZeRO-2 OOMs at 132/143GB |
| lr | 2e-5 | cosine schedule |
| warmup | 3% | |
| epochs | 1 | 2 epochs overfits (v2.8 proved) |
| seq_len | 32768 | 80% of LW truncated at 8192 |
| batch_size | 1 per GPU | |
| grad_accum | 4 | effective batch = 1×4×8GPU = 32 |
| save_steps | 200 | Checkpoint ~62GB on HF (ZeRO-3 consolidates) |
| save_total_limit | 3 | |
| agent_template | hermes | Required for NW tool_calls |

## v2.28 Results — Breakthrough

| Checkpoint | GAME | NW | LW | SWE-I |
|-----------|------|-----|-----|-------|
| ckpt600 | 36.2 | **44.1** | 38.5 | 0.0 |
| ckpt800 | **40.1** | 37.5 | 37.6 | 4.6 |
| ckpt1200 | 39.4 | 39.7 | 39.7 | 5.3 |
| ckpt2000 | 35.3 | 32.8 | **44.5** | **17.4** |

### Spatial Games Breakthrough
- hex: 0% → **57.1%**, othello: 0% → **28.6%**, clobber: 0% → **7.1%**
- Full FT's 380x parameter capacity unlocked what QLoRA never could

### Overfitting Pattern
- GAME 67% of data → GAME/NW peak at ckpt800-1200, then degrade
- LW/SWE (14% of data) keep improving through ckpt2000
- **v2.29 fix**: rebalance GAME from 67% to ~40%

## Loss Convergence (Full FT)
- Initial: ~1.0 (step 1)
- Rapid drop: ~0.50 by step 100
- Converged: 0.30-0.40 by step 500+
- Training speed: ~29s/step on 8x H200

## Tool Calling
- Training: ms-swift auto-handles via hermes agent template
- Inference: sglang with `--tool-call-parser qwen25`
- **NO reasoning-parser** — A/B tested, hurts all envs

## Critical Rules
1. **Never upload HF during training** — caused m3 crash (I/O + RAM conflict)
2. **Container rebuilds** — all persistent data on /data mount, setup auto-recovers
3. **CUDA toolkit required** — DeepSpeed JIT needs nvcc
4. **Data must be shuffled** — prevents schema inference bugs
5. **epochs=1 only** — 2 epochs overfits catastrophically
6. **Early stopping by env** — different envs peak at different checkpoints
