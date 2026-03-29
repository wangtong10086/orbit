# Trainer Short-Term Memory — 2026-03-29 09:22 UTC

## Current Status
- **m3**: v2.28 155k training running, step 400/4846 (8.3%), loss 0.41, token_acc 86.9%
  - Data: 155,077 rows (32 filtered, 0.02%)
  - Checkpoint-200 saved (428GB), checkpoint-400 just saved
  - Speed: ~28.5s/step, ETA ~1.5 days
  - Disk: 518GB/2TB (26%)
- **m1**: Eval of 155k ckpt200 running
  - GAME: 1/100 done, NW: starting, LW: initializing
  - sglang dp=4 on 4 GPUs, model loaded from HF

## Key Context
- This is 155k training (restarted from scratch with expanded data)
- Previous 87k training proved GAME 34.0 from ckpt200 (Full FT >> QLoRA 29.70)
- NW was 0 (tool_calls stripped by ms-swift) — now auto-converted before training
- LW was 0 (data filtered) — data role regenerated with 3-msg format (19776 entries)
- Data mix: GAME 103592, MG 20000, LW 19776, NW 10006, SWE-I 1735

## 155k ckpt200 Eval on m1
- Uploaded model-only (62GB) to HF: monokoco/affine-qwen3-32b-v2.28-155k-ckpt200
- Downloaded on m1, deployed sglang dp=4
- Eval running: GAME, NAVWORLD, LIVEWEB (100 samples each)
- **Key validation**: Does NW now score? (tool_call conversion fix)
- **Key validation**: Does LW now score? (3-msg format fix)

## Loss Trend (155k training)
| Step | Loss | Token Acc |
|------|------|-----------|
| 100 | 0.503 | 84.9% |
| 200 | 0.453 | 85.6% |
| 330 | 0.457 | 86.0% |
| 380 | 0.405 | 86.3% |
| 390 | 0.362 | 88.0% |
| 400 | 0.406 | 86.9% |

## CLI Tools
- `forge remote -m m3 setup` — one-click init
- `forge train launch -m m3` — auto-converts data, launches training
- `forge train monitor -m m3` — training progress
- `forge remote -m m1 kill sglang` — kill serving

## Data Quality Gate
- 155k training: 32/155109 filtered (0.02%) — well within 1k limit
- Auto-conversion: `scripts/convert_openai_to_msswift.py` runs before each training
- LW: regenerated 3-msg format (no tool_calls at all)
