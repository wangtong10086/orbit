# SWE-Infinite Environment

## Evaluation

Model 在 Docker 容器中通过 THOUGHT + bash 多轮交互修复真实 GitHub PR bug。二进制评分 0/1。

```
problem_statement → model issues bash commands → sees real output → fixes code → submits → tests run → score
```

**Response format**: `THOUGHT: [reasoning]\n\n```bash\ncommand\n```\n`
- ONE bash block per turn, NO `<think>` tags, commands in subshells
- Submit: `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && git add -A && git diff --cached`

## Task Source

- **Private R2 pool**: `affine-swe-infinite-private` (~5000+ tasks, growing ~150/day)
- Docker images: `affinefoundation/swe_infinite_images` + local build fallback
- Languages: Go ~56%, Ruby ~17%, Python ~13%, Rust ~9%, JS ~3%

## Current Status (2026-03-30)

- **1935 canonical trajectories** (Go 98.4%, Rust 0.6%, JS 0.6%, Ruby 0.4%)
- 486 unique repos, avg 13.3 turns per trajectory
- Canonical: `data/canonical/swe_infinite.jsonl`
- HF: `monokoco/affine-sft-data/swe_infinite.jsonl` — synced
- Daemon: GPT-5.4, 20 workers, 6h poll, max 5 attempts per task
- 1824 tasks exhausted (permanently skipped after 5 failures)

## Eval-Training Alignment (verified)

- **System prompt**: 542 chars, exact match between distill script and eval config
- **Instance template**: All keywords match (COMPLETE_TASK, /app, subshell, THOUGHT)
- **Observation format**: `<returncode>`, `<output>`, `<warning>` tags match eval
- **Action regex**: `` ```bash\s*\n(.*?)\n``` `` — identical
- **Submit marker**: `COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT` — identical
- **Output truncation**: 10000 chars — identical

## Distillation Scripts

| Script | Purpose | Status |
|--------|---------|--------|
| `scripts/swe_distill.py` | Per-task distillation (worker) | Active |
| `scripts/swe_continuous_distill.py` | Daemon (polls R2, manages workers) | Active on m1 |
| `scripts/swe_check_format.py` | Format validation | Utility |
| `scripts/swe_coverage_check.py` | R2 pool coverage audit | Utility |
| `scripts/swe_pool_audit.py` | R2 pool analysis | Utility |
| `scripts/swe_launch.py` | Remote batch launcher | Utility |

## Dead Ends

- **Synthetic trajectories**: fake observations, teaches wrong distribution
- **Think tags**: conflicts with THOUGHT format
- **Ruby/Rust/Python distillation**: GPT-5.4 success rate <2%
- **Docker prune -a**: destroys base images — use targeted prune only
- **seq < 16384**: 69% of trajectories truncated at seq=8192
