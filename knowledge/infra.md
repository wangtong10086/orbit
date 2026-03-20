# Infrastructure Knowledge

## Current Machine
- **4xH200** (576GB VRAM, 2.8T disk) — dedicated rental via Targon
- Online, stable since 2026-03-19
- Training: torchrun DDP across all 4 GPUs
- Eval: sglang dp=4 tp=1 (4x throughput)
- Access: `forge rental exec`, `forge rental status`

## Key Commands
```bash
forge rental status                    # GPU/disk/screens
forge rental exec "<command>"          # Remote command
forge rental start-sglang <model> --tp 4  # Deploy inference (training)
forge rental start-eval <model> --envs GAME,NAVWORLD,LIVEWEB --samples 100
forge rental kill sglang|eval|training|all
```

## sglang Setup
- Install in venv: `pip install sglang[all]`
- Training inference: `--tp 4` (all GPUs, one model instance)
- Eval inference: `--dp 4 --tp 1` (4 instances, 4x throughput)
- **Critical**: `--tool-call-parser qwen25` for NAVWORLD/LIVEWEB tool calling
- Without tool-call-parser, `<tool_call>` text is not parsed into OpenAI format

## Eval Setup
- `scripts/eval_envs.py` — runs affinetes SDK evaluations
- Requires Docker with host_network=True
- Concurrency 4, timeout 7200s (long games need time)
- AMAP_MAPS_API_KEY needed for NAVWORLD
- SWE-Infinite: needs Docker images from DockerHub (affinefoundation/swe_infinite_images)

## Pre-Quantized Model
- `unsloth/Qwen3-32B-bnb-4bit`: 4 safetensors, ~18GB, ~90s download
- vs `Qwen/Qwen3-32B`: 16 safetensors, ~65GB, 10-30 min
- Always use pre-quantized

## Targon Serverless (historical, not current primary)
- H200 $2.40/hr, used for earlier training runs
- Network intermittent, offline wheel bundle needed
- HF upload callback corrupts after step 200-300 → subprocess fork fix
- Currently not used (dedicated 4xH200 is primary)

## Cost Reference
- Training run (4xH200, ~3h): ~$9
- Eval run (3 envs, 100 samples each): ~$5-7
- Old repo total (v5-v12): ~$200
