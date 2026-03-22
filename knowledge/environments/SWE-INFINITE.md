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

- **Private R2 pool**: `affine-swe-infinite-private` (~2500 tasks, daily growth)
- Docker images: `affinefoundation/swe_infinite_images` + local build fallback
- Languages: Go ~56%, Ruby ~17%, Python ~13%, Rust ~9%, JS ~3%

## Distillation Pipeline

**Machine**: m2 (Targon rental, `wrk-2g5l02247zvp@ssh.deployments.targon.com`)
**Script**: `scripts/swe_distill.py --task-file <tasks.jsonl> --output <out.jsonl> --resume`

```
R2 task → docker pull (or local build fallback) → GPT-5.4 agent loop
→ extract patch → verify tests in fresh container → score=1.0 only → JSONL
```

**Config**: 15x retry, 1800s timeout, 15-120s backoff, auto re-queue API failures, auto Docker prune

**Local build fallback**: When `docker pull` fails, builds from `FROM golang:1.22` (etc) + `git clone` + `git checkout <commit>`. Base images pre-pulled on machine.

## Current Status

- **39 verified trajectories** (Go 35, Ruby 3, Rust 1)
- Sources: public R2 batch_v2 (22) + private R2 (16) + v4 batch (growing)
- Canonical: `data/canonical/swe_infinite.jsonl`
- HF: `monokoco/affine-sft-data/swe_infinite.jsonl` — synced
- **v4 batch RUNNING** (2026-03-22): 200 Go + 100 Ruby/Rust tasks, two parallel processes on m2
- DockerHub rate limit resolved — all 5 base images cached
- Monitor: `forge data swe-status` / Sync: `forge data swe-sync`

## Dead Ends

- **Synthetic trajectories**: fake observations (11K chars vs real 36K), teaches wrong distribution
- **Think tags**: conflicts with THOUGHT format
- **seq < 16384**: conversations truncated
- **Short timeout/few retries**: API proxy needs 1800s timeout + 15x retry
- **DockerHub rate limit**: pre-pull base images once, or use local build fallback
