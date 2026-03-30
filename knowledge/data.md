# Data Knowledge

## Current Canonical Data (2026-03-30)

| Env | Count | File | Format | Notes |
|-----|-------|------|--------|-------|
| GAME | 103592 | game.jsonl | messages, no think, no tools | All 7 games, MCTS bots, bare action IDs |
| GAME v18 | 59000 | TBD | rebalanced | Cut saturated games (goof 10k→3k, clobber 28k→10k, liars 19k→5k) |
| MemoryGym | 20000 | memorygym.jsonl | messages, no tools | ChromaDB interaction, very long (P50=49k tokens) |
| LW | 19776 | liveweb.jsonl | messages, 3-msg single-step | goto+stop only, ms-swift compatible |
| NW | 10006 | navworld.jsonl | messages + tool_calls | 7 types balanced, GPT-5.4, hermes agent template |
| SWE-I | 1735 | swe_infinite.jsonl | messages, THOUGHT+bash | Go ~95%, no think tags |

## v2.28 Training Lessons (Critical)

### Data Balance
- **GAME at 67% caused overfitting**: GAME/NW peaked at ckpt800-1200, then degraded
- **LW/SWE at 14% benefited from longer training**: kept improving through ckpt2000
- **v2.29 target**: GAME ~40%, NW ~15%, LW ~20%, MG ~15%, SWE-I ~10%

### Per-Game Results (ckpt1200)
| Game | Score | Data | Status |
|------|-------|------|--------|
| goofspiel | 86.7% | 10k→3k | Saturated, cut waste |
| hex | **57.1%** | 15k | **BREAKTHROUGH** — keep all |
| gin_rummy | 49.4% | 8k | Improved |
| othello | **28.6%** | 13k | **BREAKTHROUGH** — keep all |
| leduc_poker | 38.9% | 5k | Regressed from dilution |
| liars_dice | 6.7% | 5k | Regressed from dilution |
| clobber | 7.1% | 10k | SFT ceiling |

### Framework
- **ms-swift 4.0.2** — handles chat template, tool_calls, loss masking automatically
- **hermes agent template** — required for NW tool_calls
- **Mixed schema**: 24% entries have tool_calls. ms-swift handles natively.
- **Combined JSONL must be shuffled**

### Training Config
- Full FT Qwen3-32B (32.8B trainable), DeepSpeed ZeRO-3 + CPU offload
- 8x H200, seq=32768, per_device=1, grad_accum=4, lr=2e-5 cosine
- ~29s/step, save_steps=200, save_total_limit=3
- **Never upload HF during training** — caused crash
- **Checkpoint = ~62GB** on HF (ZeRO-3 consolidates on save)

## Storage
- Canonical: `data/canonical/*.jsonl`
- HF: `monokoco/affine-sft-data` (private)
- Training: combined.jsonl (shuffled mix of all envs)
- CLI: `forge data build-training [-m m3]`
