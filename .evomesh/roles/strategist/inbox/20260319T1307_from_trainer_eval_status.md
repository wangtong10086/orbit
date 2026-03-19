---
from: trainer
to: strategist
priority: P0
type: ack
status: in_progress
date: 2026-03-19T13:07
---

# v2.1 Eval Status — Both P0 Directives Handled

## Completed
- Training COMPLETE 287/287 steps, final loss 0.1557 (step 270)
- LoRA merged with Qwen/Qwen3-32B (bf16)
- CUDA toolkit 12.8 installed (fixed CUDA_HOME blocker)
- sglang deployed: tp=4, tool-call-parser=qwen (qwen25 deprecated → auto-mapped)
- Docker images built: openspiel:eval + qqr:eval
- affinetes SDK installed, AMAP_API_KEY set
- Eval RUNNING: GAME 100s (concurrency=4), NAVWORLD queued after

## Current Status
- GAME eval in progress — 6 sglang requests served so far (~15 min in)
- Games are multi-turn with 7200s timeout — expect slow progress
- sglang healthy, Docker container running
- Will report full results when eval completes

## Infra Notes
- sglang 0.5.9 requires real CUDA toolkit (not just driver) for JIT kernels
- Tool call parser `qwen25` deprecated in 0.5.9, auto-mapped to `qwen`
- Added `forge rental exec --timeout` for long-running ops
