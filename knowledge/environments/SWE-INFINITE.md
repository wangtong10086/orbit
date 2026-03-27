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

- **1037 canonical trajectories** (Go 1027, Rust 5, Ruby 4, JS 1) — target 500 exceeded 2x
- Avg 13.3 assistant turns per trajectory (range 4-40)
- Format: 100% audit pass (THOUGHT+bash, no think tags, no tool_calls)
- Canonical: `data/canonical/swe_infinite.jsonl`
- HF: `monokoco/affine-sft-data/swe_infinite.jsonl` — synced (1037)
- **m2 terminated** (2026-03-26) — no compute for distillation
- R2 pool: ~3500+ tasks (grows ~150/day), ~1026 attempted
- Monitor: `forge data swe-status` / Sync: `forge data swe-sync`

## v4 Batch Analysis

- Go fix rate: 54% when DockerHub image available (13/24 actual attempts)
- 176/200 infra fail = DockerHub images missing for most tasks
- Top repos: dnscontrol (5/5), terraformer (3/4), supermq, participle
- Ruby/Rust: 0% success — corrupt patches, language complexity
- **Lesson**: Focus exclusively on Go, DockerHub image availability is the bottleneck

## Data Quality Analysis (2026-03-27)

- **Seq length truncation**: At seq=8192 (training config), only 31.3% fit untruncated. At seq=16384, 80.2% fit.
- Token distribution: 4.5% <4K, 26.8% 4-8K, 29.2% 8-12K, 19.6% 12-16K, 19.8% >16K
- Avg 13.3 assistant turns (median 11, range 4-40)
- 336 unique repos — good diversity
- Top repos: istio (41), go-micro (39), gitea (36), terraform-provider-google (33)
- Efficient trajectories (<= 8 turns): 284 (27.4%), 68% fit seq=8192. Targeted fixes.
- Verbose trajectories (>= 20 turns): 167 (16.1%), only 3% fit seq=8192. Mostly wasted at seq=8192.
- First command: 49% start with `cd`, 29% `ls`, 19% `find` — exploration-heavy
- **Recommendation**: At seq=8192, filter to short trajectories (325 fit). At seq=16384, use full set (832 fit).

## Eval-Training Alignment (verified 2026-03-27)

- **System prompt**: Training uses short `system_template` (542 chars) — matches eval exactly
- **Instance template**: Full instructions (`/app`, `COMPLETE_TASK_AND_SUBMIT`, subshell rules) sent as first user msg — matches eval
- **Observation format**: `<returncode>`, `<output>`, `<warning>` tags match eval's `action_observation_template`
- **Scoring**: Binary 1.0/0.0 — ALL `fail_to_pass` AND `pass_to_pass` tests must pass. No partial credit.
- **Max iterations**: 100 steps in eval. Training avg is 13.3 turns (well within limit).
- **Alignment status**: GOOD — no format mismatches detected

## Dead Ends

- **Synthetic trajectories**: fake observations (11K chars vs real 36K), teaches wrong distribution
- **Think tags**: conflicts with THOUGHT format
- **seq < 16384**: conversations truncated
- **Short timeout/few retries**: API proxy needs 1800s timeout + 15x retry
- **DockerHub rate limit**: use `mirror.gcr.io/library/<image>` as fallback (no rate limit). Script auto-falls back.
- **Ruby/Rust distillation**: GPT-5.4 cannot reliably fix — 0/100 success rate
- **Python distillation**: 0/8 so far (v5 batch) — complex deps, test failures even when patch correct
- **Docker prune -a**: destroys base images — use targeted swe-local prune only
