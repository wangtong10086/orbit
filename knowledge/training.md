# Training Knowledge

## Key Facts
- Base model: Qwen/Qwen3-32B (always train from base, not from other fine-tunes)
- Pre-quantized: unsloth/Qwen3-32B-bnb-4bit (18GB vs 65GB, ~90s download)
- Method: QLoRA (4-bit NF4)
- Training from top model (#2) failed: loss oscillated wildly, QLoRA cannot stably learn on deeply-tuned models
- SFT 1 epoch is sufficient; 2 epochs overfits small datasets (v2.8: LIVEWEB 438 samples → score 4.0 vs 13.76 at 1 epoch)
- Machine: 4xH200 (576GB VRAM total)

## Current Config (v2.7+)

| Param | Value | Notes |
|-------|-------|-------|
| lr | **5e-5** | v2.7 winner. 1e-4 too aggressive (v2.6), 1e-5 too low (v1-v3) |
| LoRA r | **64** | r=16 insufficient, r=128 marginal benefit |
| LoRA alpha | **128** | 2x rank |
| epochs | **1** | 2 epochs overfits LIVEWEB (v2.8: 4.0 vs 13.76). 3 epochs → catastrophic forgetting |
| seq_len | **8192** | seq=8192 wins GM (v2.4a vs v2.4b). 16384 helps LIVEWEB but hurts NAVWORLD |
| batch | **2** | per GPU at seq=8192 |
| grad_accum | **2** | effective batch = 4 GPUs × 2 × 2 = 16 |
| packing | **True** | 2-3x efficiency; Unsloth latest fixes cross-sequence contamination |
| warmup | **3%** | |
| max_grad_norm | **0.3** | |
| num_gpus | **auto** | Must use ALL GPUs (user directive) |
| ddp | **True** | 4xH200 DDP via torchrun |

## Training History

| Ver | Data | seq | lr | Steps | Tokens | Loss | GAME | NW | LW |
|-----|------|-----|-----|-------|--------|------|------|-----|-----|
| v2.1 | 6894 | 8192 | 1e-4 | ~430 | 56.4M | **0.156** | 25.74 | **8.47** | — |
| v2.2 | 7239 | 16384 | 1e-4 | 162 | 42.5M | 0.224 | 26.04 | 6.10 | 6.83 |
| v2.3 | 7626 | 16384 | 1e-4 | 194 | 50.9M | 0.172 | 22.69 | 1.52 | 8.62 |
| v2.4a | 5120 | 8192 | 1e-4 | ~160 | 21.0M | 0.231 | 26.03 | 7.71 | 11.90 |
| v2.4b | 5278 | 16384 | 1e-4 | 125 | 32.8M | 0.170 | 25.44 | 4.58 | **15.77** |
| v2.5 | 5533 | 16384 | 1e-4 | 134 | 35.1M | 0.288 | 24.28 | 6.51 | 11.82 |
| v2.6 | 6191 | 8192 | 1e-4 | 268 | 35.1M | 0.301 | **26.66** | 5.82* | 11.73 |
| v2.7 | 6204 | 8192 | 5e-5 | 268 | 35.1M | 0.243 | eval | eval | 13.76 |

*NAVWORLD without CHUTES LLM score (code only, max 50)

## Training Intensity Analysis (KEY INSIGHT)

v2.1 (best NAVWORLD) processed **56.4M tokens** in ~430 steps.
v2.6/v2.7 processed only **35.1M tokens** in 268 steps — **38% less training**.
This explains why loss stays 0.24-0.30 instead of converging to 0.15.

Formula: total_tokens = steps × seq_len × effective_batch
- effective_batch = n_gpus × batch_per_gpu × grad_accum

**v2.8 fix**: epochs=2, lr=7e-5 → ~536 steps, ~70M tokens, target loss <0.20.

## Loss Convergence Pattern
- Initial: ~0.62 (step 10)
- Rapid drop: ~0.40 by step 50
- Plateau: ~0.19-0.25 by step 100
- Converged: 0.15-0.20 (needs 400+ steps)
- **Under-trained**: >0.25 at end = not enough steps
- Abnormal: >0.5 after step 50 → terminate immediately
- More data/envs → slightly higher final loss (expected)

## Training Speed (4xH200 DDP)
- seq=16384, batch=1: ~54s/step
- 7000-8000 samples: ~190-200 steps, ~3 hours
- VRAM: 88-90GB/144GB per GPU

## v2.23 Key Lessons

1. **LW single-turn + tools field = breakthrough** — 12054 single-turn entries with tools field matching eval template → LW 17.68 (new best, +12% vs v2.4b)
2. **reasoning-parser qwen3 BREAKS tool-call envs** — puts tool_calls into reasoning_content field. A/B: NW 34.88 (without) vs 18.86 (with). DO NOT USE.
3. **Optimal checkpoint ≠ final** — ckpt-550 beats ckpt-657: NW 34.88 vs 27.58, LW 17.68 vs 13.96. Late training overfits. Use ~84% of total steps.
4. **LW volume dilutes NW** — 12054 LW (48% of data) pushed NW from 42.34 → 34.88. v2.17a had only 14% LW. Keep LW ≤30% of mix for NW protection.

## Tool Calling (NAVWORLD + LIVEWEB critical)
- Training: `tokenizer.apply_chat_template(messages, tools=tools)` → Qwen3 native format
- Inference: sglang with `--tool-call-parser qwen25`
- Both required — without either, tool-call envs score 0
- **Known sglang bugs with qwen25 parser**:
  - Issue #9184: tool_call tags leak into content
  - Fallback order: qwen25 → hermes → Qwen-Agent built-in

## DPO Pipeline (built, unused)
- 2688 preference pairs: GAME 589, LGC-v2 800, NAVWORLD 241, PRINT 800, SWE-SYNTH 258
- Config: beta=0.1, lr=5e-6, batch=1, grad_accum=8
- CLI: `forge train dpo-launch`

## SFT Plateau Response (GRPO/RL NOT allowed — user directive)

When SFT plateaus, improve via data quality:
- Redesign think format (rule-based instead of MCTS stats)
- Better format alignment with eval (tools params, system prompts)
- More diverse examples, not just more quantity
- Structural zero → data redesign, not method change
