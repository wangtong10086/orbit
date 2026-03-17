# Infrastructure Knowledge

## Key Facts
- GPU: Targon serverless (H200 $2.40/hr, H200-M 2x $4.80/hr) or dedicated rentals (4xH200)
- Training CLI: `python3 -m forge train launch` / `forge rental` commands
- Eval: `scripts/eval_envs.py` with affinetes SDK, requires Docker + host_network=True
- Inference: sglang with tp=4 on 4xH200, port 30000

## Targon Serverless Quirks

### Supported Images
- `nvidia/cuda:12.4.0-devel-ubuntu22.04` — verified working
- `pytorch/pytorch:2.5.1-cuda12.4-cudnn9-devel` — works since ~2026-03-12 (previously broken)
- `nvcr.io/nvidia/pytorch:24.10-py3` — does NOT work (zero logs)
- NGC images — do NOT work

### Network Issues (Intermittent)
- Outbound network can be completely down for hours
- When available, only ~30-60s window after container startup
- apt-get (47MB) fits in window; pip install torch (2GB) usually does not
- Network wait loop needed: 60x10s probing `/dev/tcp/pypi.org/443`

### Workaround: Offline Wheel Bundle
- Pre-download all Python dependency wheels (202MB tar.gz)
- Upload to HF dataset repo (`ml-deps.tar.gz`)
- Container downloads via urllib (reliable, ~30s), then `pip install --no-index --find-links`
- Critical: include correct bitsandbytes version (>=0.46.1 for transformers compat)

### Log Issues
- Targon logs API buffer is very small, only keeps recent lines
- tqdm progress bar uses `\r`, invisible in SSE logs
- PyTorch image logs may return 500 from API
- Workaround: HTTP status endpoint (`/tmp/health/status.json` via http.server)

### Container Behavior
- No persistent storage between containers
- Health check server recommended (http.server on port 80)
- `(cmd &)` subshell isolation needed for backgrounding (bare `&` has bugs)
- pip install from scratch takes ~15 minutes (unavoidable if no wheel bundle)

## HF Upload Callback Bug
- HfApi instance corrupts after long-running training (~step 200-300)
- Connection pool/auth state breaks, all subsequent uploads silently fail
- **Attempted fixes that failed**: reduce frequency, new HfApi instance, 3 retries + backoff
- **Working fix**: Fork independent Python subprocess per upload, pass params via JSON, 300s timeout

## Wheel Bundle Contents
- torch, transformers, trl, peft, bitsandbytes (>=0.49.2), accelerate, datasets
- 202MB tar.gz on HF dataset repo
- Must update when upgrading library versions (e.g., torch>=2.6 for CVE-2025-32434)

## Pre-Quantized Model
- `unsloth/Qwen3-32B-bnb-4bit`: 4 safetensors, ~18GB, ~90s download
- vs `Qwen/Qwen3-32B`: 16 safetensors, ~65GB, 10-30 min download
- Always use pre-quantized for Targon serverless

## sglang Setup
- Install in venv: `pip install sglang[all]`
- CUDA toolkit needed: `cuda-nvcc-12-8 + cuda-cudart-dev-12-8`
- Launch: `python -m sglang.launch_server --model <path> --tp 4 --port 30000`
- **Critical**: Add `--tool-call-parser qwen25` for NAVWORLD tool calling
- Without tool-call-parser, `<tool_call>` text is not parsed into OpenAI format

## Eval Setup
- `scripts/eval_envs.py` — runs affinetes SDK evaluations
- Requires Docker with host_network=True
- Concurrency 4, timeout 7200s (not 600s — long games need time)
- AMAP_MAPS_API_KEY env var needed for NAVWORLD
- SWE-SYNTH needs external breaker service (cannot eval locally)
- LIVEWEB needs predefined task set (cannot eval locally)

## Rental Workflow
```bash
forge rental status                    # Check GPU status
forge rental start-sglang <model> --tp 4  # Deploy inference
forge rental start-eval <model> --envs GAME,NAVWORLD --samples 100
forge rental kill sglang|eval|training|all
forge rental exec "<command>"          # Run command on rental
```

## Current Best / Status
- Dedicated rental `rentals-w58tlzhv9xyh3dis` (4xH200) active
- Wheel bundle approach reliable for Targon serverless
- HF subprocess upload fix verified working

## Cost Summary
- Targon debugging/failures: ~$50+ total across all iterations
- Successful training runs: $7-14 each
- Average iteration cost: ~$10-15 (training) + $5-10 (eval rental time)
