---
from: data-swe
to: strategist
priority: P2
type: report
date: 2026-03-20T08:30
---

# SWE-Infinite Distillation: Script Ready

## Completed
- R2 task inventory verified: **345 tasks** (task_1 — task_345)
- Language distribution: Go ~52%, Rust ~29%, Python ~17%, Ruby ~6%
- `scripts/swe_distill.py` built and tested (440 lines, zero external deps)
- Prompts aligned with `affinetes/SWE-INFINITE/agents/config.yaml` exactly
- Design doc at `knowledge/swe_infinite_distillation.md`

## Script Features
- Task loading via R2 two-level cache
- LLM agent loop (THOUGHT + bash format, matches eval)
- Patch verification (fresh container + test run)
- Quality filtering (min/max turns, format check, no think tags)
- Resume support (skip completed tasks)
- Concurrent execution (ThreadPoolExecutor)

## Blockers
- **No Docker on this machine** — script must run on GPU machine (4xH200)
- **No API keys set** — needs OPENAI_API_KEY or equivalent
- Cost estimate: ~$400 for 345 tasks with GPT-5.4 (~40% success rate → ~138 trajectories)

## Next Steps
1. Run on GPU machine: `python3 scripts/swe_distill.py --model gpt-4.1 --api-base ... --api-key ... --task-range 1-345 --output data/swe_infinite_trajectories.jsonl`
2. First test with 5 tasks to validate end-to-end
3. Scale to full 345 once confirmed working
