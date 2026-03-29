# Real Test Report

- Date: 2026-03-29
- Operator: Codex
- Milestone: cross-milestone runbook execution
- Scope: `docs/refactor/real-test-plan.md`
- Git commit: `ad1be41`
- Branch: `refactor/three-layer-architecture`
- Environment: local workspace plus remote SSH machine `m1`
- Provider(s): local CLI, SSH backend, Targon backend
- Machine(s): local host, `m1`
- Image(s): `wangtong123/affine-forge:latest` referenced only, not built in this run
- Overall result: partial

## Summary

| Test ID | Status | Command / Evidence | Artifact Path | Log Path | Notes |
|---|---|---|---|---|---|
| 0.1.1 | pass | `.env` exists | `n/a` | `n/a` | `test -f .env` returned present |
| 0.1.2 | pass | `HF_TOKEN` key present in `.env` | `n/a` | `n/a` | key name present, value not printed |
| 0.1.3 | pass | `HF_DATASET_REPO` prerequisite check | `n/a` | `n/a` | key now present and config-loaded |
| 0.1.4 | pass | `TARGON_API_KEY` key present in `.env` | `n/a` | `n/a` | key name present, value not printed |
| 0.1.5 | pass | AMap key prerequisite check | `n/a` | `n/a` | `AMAP_API_KEY` now present |
| 0.1.6 | pass | NAVWORLD LLM key prerequisite check | `n/a` | `n/a` | `QWEN_API_KEY` and `CHUTES_API_KEY` now present |
| 0.1.7 | pass | `machines.json` exists | `n/a` | `n/a` | machine file present |
| 0.2.1 | pass | `./.venv/bin/python -m pytest -q` | `n/a` | `logs/real-tests/2026-03-29/MX-logs/0.2.1.log` | `181 passed in 0.99s` |
| 0.2.2 | pass | `./.venv/bin/python -m forge --help` | `n/a` | `logs/real-tests/2026-03-29/MX-logs/0.2.2.log` | root CLI visible |
| 0.2.3 | pass | `./.venv/bin/python -m forge remote --help` | `n/a` | `logs/real-tests/2026-03-29/MX-logs/0.2.3.log` | remote family visible |
| 0.2.4 | pass | `./.venv/bin/python -m forge train --help` | `n/a` | `logs/real-tests/2026-03-29/MX-logs/0.2.4.log` | train family visible |
| 0.2.5 | pass | `./.venv/bin/python -m forge eval --help` | `n/a` | `logs/real-tests/2026-03-29/MX-logs/0.2.5.log` | eval family visible |
| 1.1.1 | pass | environment catalog listing | `n/a` | `logs/real-tests/2026-03-29/MX-logs/1.1.1.log` | explicit catalog import worked |
| 1.2.1 | pass | strict geo mean check | `n/a` | `logs/real-tests/2026-03-29/MX-logs/1.2.1.log` | `basic=6.0`, `zero=0.0`, `empty=0.0` |
| 1.3.1 | pass | Qwen3 packer on canonical NAVWORLD sample | `data/canonical/navworld.jsonl` | `logs/real-tests/2026-03-29/MX-logs/1.3.1.log` | `<tool_call>` formatting present |
| 1.4.1 | pass | `LocalCanonicalRepository` temp-dir write/reload | `n/a` | `logs/real-tests/2026-03-29/MX-logs/1.4.1.log` | append and reload stable |
| 2.1.1 | pass | `forge data validate tmp/sample_game.jsonl --env GAME` | `tmp/sample_game.jsonl` | `logs/real-tests/2026-03-29/MX-logs/2.1.1.log` | 1/1 passed |
| 2.1.2 | fail | `forge data validate tmp/sample_navworld.jsonl --env NAVWORLD` | `tmp/sample_navworld.jsonl` | `logs/real-tests/2026-03-29/MX-logs/2.1.2.log` | sample failed `final_short` |
| 2.1.3 | fail | `forge data validate tmp/sample_game_bad.jsonl --env GAME` | `tmp/sample_game_bad.jsonl` | `logs/real-tests/2026-03-29/MX-logs/2.1.3.log` | failure reported, but without actionable issue detail |
| 2.2.1 | pass | dry-run ingest | `logs/real-tests/2026-03-29/MX-artifacts/navworld_count_before.txt` | `logs/real-tests/2026-03-29/MX-logs/2.2.1.log` | duplicate detected, no write |
| 2.2.2 | pass | real ingest without upload | `logs/real-tests/2026-03-29/MX-artifacts/navworld_count_after.txt` | `logs/real-tests/2026-03-29/MX-logs/2.2.2.log` | duplicate skipped, total unchanged |
| 2.3.1 | fail | `forge data aggregate --envs GAME,NAVWORLD -o tmp/train_smoke.jsonl --no-upload` | `n/a` | `logs/real-tests/2026-03-29/MX-logs/2.3.1.log` | CLI callback mismatch: unexpected `remote_name` |
| 2.3.2 | not_run | inspect aggregate output | `n/a` | `n/a` | blocked by 2.3.1 failure |
| 2.4.1 | pass | `forge data status` | `synth_config.json` | `logs/real-tests/2026-03-29/MX-logs/2.4.1.log` | command read repo-root config successfully |
| 2.5.1 | pass | `forge data navworld-gen -n 2 --type half_day -o tmp/navworld_smoke_rerun.jsonl` | `logs/real-tests/2026-03-29/MX-artifacts/navworld_smoke_rerun_count.txt` | `logs/real-tests/2026-03-29/MX-logs/2.5.1-rerun.log` | generated `2/2` samples successfully |
| 2.5.2 | pass | `forge data validate tmp/navworld_smoke_rerun.jsonl --env NAVWORLD` | `tmp/navworld_smoke_rerun.jsonl` | `logs/real-tests/2026-03-29/MX-logs/2.5.2-rerun.log` | validation `2/2` passed |
| 2.6.1 | pass | `forge data swe-status` | `n/a` | `logs/real-tests/2026-03-29/MX-logs/2.6.1.log` | explicit infra failure reported for remote `m2` SSH auth |
| 2.6.2 | fail | `forge data swe-sync --dry-run` | `n/a` | `logs/real-tests/2026-03-29/MX-logs/2.6.2.log` | permission failure was parsed as integer and crashed |
| 3.1.1 | pass | `forge remote machine -m m1 status` | `n/a` | `logs/real-tests/2026-03-29/MX-logs/3.1.1.log` | `m1` online with H200 GPUs |
| 3.1.2 | pass | `forge remote machine -m m1 exec 'echo ok && hostname && nvidia-smi -L'` | `n/a` | `logs/real-tests/2026-03-29/MX-logs/3.1.2.log` | remote exec returned hostname and 8 GPUs |
| 3.1.3 | pass | `forge remote machine -m m1 upload README.md /tmp/README.md` | `README.md` | `logs/real-tests/2026-03-29/MX-logs/3.1.3.log` | upload completed |
| 3.1.4 | fail | `forge remote machine -m m1 sync` | `n/a` | `logs/real-tests/2026-03-29/MX-logs/3.1.4.log` | dir upload fallback only supports files |
| 3.1.5 | fail | `forge remote machine -m m1 run 'pwd'` | `n/a` | `logs/real-tests/2026-03-29/MX-logs/3.1.5.log` | same sync/upload bug as 3.1.4 |
| 3.2.1 | pass | `forge remote compute capacity` | `n/a` | `logs/real-tests/2026-03-29/MX-logs/3.2.1.log` | Targon capacity returned |
| 3.2.2 | pass | `forge remote compute list` | `n/a` | `logs/real-tests/2026-03-29/MX-logs/3.2.2.log` | listed current instances |
| 3.2.3 | pass | `forge remote compute provision --gpu h200-small --name smoke-test` | `n/a` | `logs/real-tests/2026-03-29/MX-logs/3.2.3.log` | provisioned `wrk-l0g5vf8f906r` |
| 3.2.4 | pass | `forge remote compute logs wrk-l0g5vf8f906r --tail 50` | `n/a` | `logs/real-tests/2026-03-29/MX-logs/3.2.4.log` | logs retrievable during `ContainerCreating` |
| 3.2.5 | pass | `forge remote compute terminate wrk-l0g5vf8f906r` | `n/a` | `logs/real-tests/2026-03-29/MX-logs/3.2.5.log` | terminated successfully |
| 4.1.1 | blocked | docker build on SSH machine | `n/a` | `n/a` | only SSH machine `m1` had live training; no safe dedicated builder |
| 4.1.2 | not_run | push built image | `n/a` | `n/a` | blocked by 4.1.1 |
| 4.2.1 | not_run | runtime check `docker run ... python -V` | `n/a` | `n/a` | blocked by 4.1.1 |
| 4.2.2 | not_run | runtime check `docker run ... swift --help` | `n/a` | `n/a` | blocked by 4.1.1 |
| 4.3.1 | not_run | registry accessibility for Targon image pull | `n/a` | `n/a` | no image built or pushed in this run |
| 5.1.1 | fail | `forge data aggregate --envs GAME -o tmp/train_smoke_5.jsonl --max-per-env 20 --no-upload` | `n/a` | `logs/real-tests/2026-03-29/MX-logs/5.1.1.log` | same CLI callback mismatch as 2.3.1 |
| 5.1.2 | pass | smoke model selection | `logs/real-tests/2026-03-29/MX-artifacts/selected_smoke_model.txt` | `n/a` | chose `Qwen/Qwen2.5-0.5B-Instruct` |
| 5.2.1 | blocked | SSH provider smoke launch | `tmp/game_train.jsonl` | `n/a` | unsafe to launch on active `m1`; inference from source: SSH provider does not upload dataset file |
| 5.2.2 | not_run | capture SSH training logs | `n/a` | `n/a` | blocked by 5.2.1 |
| 5.3.1 | fail | `forge train launch ... --provider targon-bootstrap ...` | `tmp/game_train.jsonl` | `logs/real-tests/2026-03-29/MX-logs/5.3.1-rerun.log` | env blocker cleared; Targon rejected generated workload name |
| 5.3.2 | not_run | capture Targon bootstrap logs | `n/a` | `n/a` | blocked by 5.3.1 |
| 5.4.1 | fail | `forge train launch ... --provider targon-image ...` | `tmp/game_train.jsonl` | `logs/real-tests/2026-03-29/MX-logs/5.4.1-rerun.log` | env blocker cleared; Targon rejected generated workload name |
| 5.4.2 | not_run | capture Targon image logs | `n/a` | `n/a` | blocked by 5.4.1 |
| 5.5.1 | pass | provider list reused from `forge remote compute list` | `n/a` | `logs/real-tests/2026-03-29/MX-logs/3.2.2.log` | provider visibility confirmed |
| 5.5.2 | pass | provider logs reused from `forge remote compute logs ...` | `n/a` | `logs/real-tests/2026-03-29/MX-logs/3.2.4.log` | log retrieval path confirmed |
| 5.5.3 | not_run | SSH status/exec as training monitor alternative | `n/a` | `n/a` | no SSH training smoke was launched |
| 6.1.1 | pass | `forge train prepare GAME -o tmp/game_train.jsonl` | `tmp/game_train.jsonl` | `logs/real-tests/2026-03-29/MX-logs/6.1.1.log` | built 1-sample GAME dataset |
| 6.1.2 | pass | `forge train prepare NAVWORLD -o tmp/navworld_train.jsonl` | `tmp/navworld_train.jsonl` | `logs/real-tests/2026-03-29/MX-logs/6.1.2.log` | built 1-sample NAVWORLD dataset |
| 6.2.1 | pass | `forge train full GAME --provider targon-bootstrap --gpu H200` | `tmp/game_train.jsonl` | `logs/real-tests/2026-03-29/MX-logs/6.2.1-rerun.log` | dataset uploaded, run launched, startup logs captured, container terminated |
| 6.3.1 | pass | `forge train full GAME --provider targon-image --gpu H200 --image ...` | `tmp/game_train.jsonl` | `logs/real-tests/2026-03-29/MX-logs/6.3.1-rerun2.log` | dataset uploaded, run launched, container reached `ContainerCreating`, then terminated |
| 7.1.1 | blocked | `forge remote machine -m m1 start-sglang <model> --tp 1 --wait` | `n/a` | `logs/real-tests/2026-03-29/MX-logs/7.probe.2.log` | no safe dedicated GPU machine; probe showed no service on port 30000 |
| 7.1.2 | not_run | reachability check after server start | `n/a` | `n/a` | blocked by 7.1.1 |
| 7.2.1 | not_run | single-env eval smoke | `n/a` | `n/a` | blocked by missing live inference endpoint |
| 7.3.1 | not_run | multi-env eval smoke | `n/a` | `n/a` | blocked by missing live inference endpoint |
| 7.4.1 | not_run | larger real evaluation run | `n/a` | `n/a` | blocked by missing live inference endpoint |
| 8.1.1 | pass | `TrainerAgent.execute()` real local run | `n/a` | `logs/real-tests/2026-03-29/MX-logs/8.1.1.log` | honest blocked outcome, no fake success |
| 8.2.1 | pass | `DataAgent.prepare()` against real canonical data | `data/canonical/game.jsonl` | `logs/real-tests/2026-03-29/MX-logs/8.2.1.log` | repository-backed path returned ready/count/path |
| 8.3.1 | pass | `EvolutionLoop.step()` real local run | `n/a` | `logs/real-tests/2026-03-29/MX-logs/8.3.1.log` | honest blocked outcome, no dry-run fake success |
| 9.1 | not_run | end-to-end ingest or generation | `n/a` | `n/a` | full vertical slice incomplete |
| 9.2 | not_run | end-to-end dataset build | `n/a` | `n/a` | full vertical slice incomplete |
| 9.3 | not_run | end-to-end training launch | `n/a` | `n/a` | full vertical slice incomplete |
| 9.4 | not_run | end-to-end inference startup | `n/a` | `n/a` | full vertical slice incomplete |
| 9.5 | not_run | end-to-end evaluation | `n/a` | `n/a` | full vertical slice incomplete |
| 9.6 | not_run | end-to-end artifact inspection | `n/a` | `n/a` | full vertical slice incomplete |

## Detailed Entries

### 0.2.1 Baseline pytest

- Status: `pass`
- Time: 2026-03-29 CST
- Commit: `ad1be41`
- Command: `./.venv/bin/python -m pytest -q`
- Inputs / config: repository working tree
- Machine / provider / image: local host
- Output artifact path: `n/a`
- Log path: `logs/real-tests/2026-03-29/MX-logs/0.2.1.log`
- Expected result: repository test suite passes
- Actual result: `181 passed in 0.99s`
- Follow-up: none

### 2.3.1 Dataset Build CLI

- Status: `fail`
- Time: 2026-03-29 CST
- Commit: `ad1be41`
- Command: `./.venv/bin/python -m forge data aggregate --envs GAME,NAVWORLD -o tmp/train_smoke.jsonl --no-upload`
- Inputs / config: `data/canonical/game.jsonl`, `data/canonical/navworld.jsonl`
- Machine / provider / image: local host
- Output artifact path: `n/a`
- Log path: `logs/real-tests/2026-03-29/MX-logs/2.3.1.log`
- Expected result: output JSONL created with packed `messages`
- Actual result: click callback crashed with `TypeError: aggregate() got an unexpected keyword argument 'remote_name'`
- Follow-up: fix `forge data aggregate` CLI signature/wiring before relying on this command as the primary dataset-build path

### 2.5.1 NAVWORLD Generation

- Status: `pass`
- Time: 2026-03-29 CST
- Commit: `ad1be41`
- Command: `./.venv/bin/python -m forge data navworld-gen -n 2 --type half_day -o tmp/navworld_smoke_rerun.jsonl`
- Inputs / config: `.env`
- Machine / provider / image: local host
- Output artifact path:
  - `tmp/navworld_smoke_rerun.jsonl`
  - `logs/real-tests/2026-03-29/MX-artifacts/navworld_smoke_rerun_count.txt`
- Log path: `logs/real-tests/2026-03-29/MX-logs/2.5.1-rerun.log`
- Expected result: generated NAVWORLD sample file
- Actual result: generated `2/2` samples successfully using `qwen3-max`
- Follow-up: none for the env-variable blocker; generation path is now unblocked

### 2.6.2 SWE Sync Dry Run

- Status: `fail`
- Time: 2026-03-29 CST
- Commit: `ad1be41`
- Command: `./.venv/bin/python -m forge data swe-sync --dry-run`
- Inputs / config: `.env`, remote `m2` path assumptions inside SWE pipeline
- Machine / provider / image: local host plus remote SSH attempt
- Output artifact path: `n/a`
- Log path: `logs/real-tests/2026-03-29/MX-logs/2.6.2.log`
- Expected result: dry-run summary or explicit infrastructure blocker
- Actual result: command crashed with `ValueError` after trying to parse an SSH permission-denied message as an integer
- Follow-up: harden `forge/data/swe_ops.py` so SSH auth failures surface as explicit blockers instead of parser crashes

### 3.1.4 Remote Sync

- Status: `fail`
- Time: 2026-03-29 CST
- Commit: `ad1be41`
- Command: `./.venv/bin/python -m forge remote machine -m m1 sync`
- Inputs / config: local `scripts/` directory, `machines.json`
- Machine / provider / image: SSH backend to `m1`
- Output artifact path: `n/a`
- Log path: `logs/real-tests/2026-03-29/MX-logs/3.1.4.log`
- Expected result: project files sync to remote host
- Actual result: rsync/scp failed on Targon SSH banner output, then fallback failed because SSH pipe upload supports files only, not dirs
- Follow-up: implement directory-capable fallback for Targon SSH deployments or avoid syncing dirs through the pipe path

### 3.1.5 Remote Run

- Status: `fail`
- Time: 2026-03-29 CST
- Commit: `ad1be41`
- Command: `./.venv/bin/python -m forge remote machine -m m1 run 'pwd'`
- Inputs / config: local project tree, `machines.json`
- Machine / provider / image: SSH backend to `m1`
- Output artifact path: `n/a`
- Log path: `logs/real-tests/2026-03-29/MX-logs/3.1.5.log`
- Expected result: sync and remote command execution
- Actual result: failed in the same directory-upload fallback path as 3.1.4 before command execution
- Follow-up: same fix as 3.1.4

### 3.2.3 Through 3.2.5 Targon Lifecycle

- Status: `pass`
- Time: 2026-03-29 CST
- Commit: `ad1be41`
- Command: `provision -> logs -> terminate`
- Inputs / config: `.env` `TARGON_API_KEY`
- Machine / provider / image: Targon backend, `h200-small`
- Output artifact path: `n/a`
- Log path:
  - `logs/real-tests/2026-03-29/MX-logs/3.2.3.log`
  - `logs/real-tests/2026-03-29/MX-logs/3.2.4.log`
  - `logs/real-tests/2026-03-29/MX-logs/3.2.5.log`
- Expected result: instance provisions, logs are readable, instance terminates
- Actual result: instance `wrk-l0g5vf8f906r` provisioned, logs showed `ContainerCreating`, terminate succeeded, post-terminate list removed the instance
- Follow-up: none for basic lifecycle

### 5.3.1 And 5.4.1 Targon Training Smoke

- Status: `fail`
- Time: 2026-03-29 CST
- Commit: `ad1be41`
- Command:
  - `./.venv/bin/python -m forge train launch tmp/game_train.jsonl --provider targon-bootstrap --model Qwen/Qwen2.5-0.5B-Instruct --epochs 1 --batch-size 1`
  - `./.venv/bin/python -m forge train launch tmp/game_train.jsonl --provider targon-image --image wangtong123/affine-forge:latest --model Qwen/Qwen2.5-0.5B-Instruct --epochs 1 --batch-size 1`
- Inputs / config: `tmp/game_train.jsonl`
- Machine / provider / image: Targon bootstrap and Targon image providers
- Output artifact path: `tmp/game_train.jsonl`
- Log path:
  - `logs/real-tests/2026-03-29/MX-logs/5.3.1-rerun.log`
  - `logs/real-tests/2026-03-29/MX-logs/5.4.1-rerun.log`
- Expected result: launch requests accepted
- Actual result: environment blockers were cleared, but both providers now fail with `WORKLOAD_INVALID_REQUEST` because the generated Targon workload name contains invalid characters
- Follow-up: sanitize the generated workload name before calling Targon `deploy_container`

### 6.1.1 And 6.1.2 Local Training Data Prep

- Status: `pass`
- Time: 2026-03-29 CST
- Commit: `ad1be41`
- Command:
  - `./.venv/bin/python -m forge train prepare GAME -o tmp/game_train.jsonl`
  - `./.venv/bin/python -m forge train prepare NAVWORLD -o tmp/navworld_train.jsonl`
- Inputs / config: local canonical files under `data/canonical/`
- Machine / provider / image: local host
- Output artifact path:
  - `tmp/game_train.jsonl`
  - `tmp/navworld_train.jsonl`
- Log path:
  - `logs/real-tests/2026-03-29/MX-logs/6.1.1.log`
  - `logs/real-tests/2026-03-29/MX-logs/6.1.2.log`
- Expected result: training files built from canonical data
- Actual result: both commands succeeded and produced inspectable one-sample outputs
- Follow-up: none for local dataset prep

### 6.2.1 And 6.3.1 Full Training Providers

- Status: `pass`
- Time: 2026-03-29 CST
- Commit: `ad1be41`
- Command:
  - `./.venv/bin/python -m forge train full GAME --provider targon-bootstrap --gpu H200`
  - `./.venv/bin/python -m forge train full GAME --provider targon-image --gpu H200 --image wangtong123/affine-forge:latest`
- Inputs / config:
  - `.env` with `HF_TOKEN`, `HF_DATASET_REPO`, `TARGON_API_KEY`
  - local canonical GAME data
- Machine / provider / image: Targon bootstrap and Targon image providers
- Output artifact path:
  - `tmp/game_train.jsonl`
  - uploaded dataset: `https://huggingface.co/datasets/monokoco/affine-sft-data/blob/main/game_train.jsonl`
- Log path:
  - `logs/real-tests/2026-03-29/MX-logs/6.2.1-rerun.log`
  - `logs/real-tests/2026-03-29/MX-logs/6.2.1-rerun-logs.log`
  - `logs/real-tests/2026-03-29/MX-logs/6.2.1-rerun-terminate.log`
  - `logs/real-tests/2026-03-29/MX-logs/6.3.1-rerun2.log`
  - `logs/real-tests/2026-03-29/MX-logs/6.3.1-rerun2-logs.log`
  - `logs/real-tests/2026-03-29/MX-logs/6.3.1-rerun2-terminate.log`
- Expected result: dataset build, upload, and launch path succeed with both providers
- Actual result:
  - bootstrap provider uploaded the dataset, launched run `wrk-cm9hisnzpdsg`, emitted startup logs (`[SETUP] Installing ms-swift...`), and was then terminated intentionally
  - image provider uploaded the dataset, launched run `wrk-48f2dud5waza`, reached `ContainerCreating`, and was then terminated intentionally
- Follow-up: none for the env-variable blocker; both provider launch paths are now unblocked

### 7.1 Inference Start Prerequisite

- Status: `blocked`
- Time: 2026-03-29 CST
- Commit: `ad1be41`
- Command / Evidence:
  - official step not executed: `./.venv/bin/python -m forge remote machine -m m1 start-sglang <model> --tp 1 --wait`
  - probe run: `./.venv/bin/python -m forge remote machine -m m1 exec 'curl -sS --max-time 5 http://127.0.0.1:30000/v1/models || true'`
- Inputs / config: remote `m1`
- Machine / provider / image: SSH backend to `m1`
- Output artifact path: `n/a`
- Log path: `logs/real-tests/2026-03-29/MX-logs/7.probe.2.log`
- Expected result: safe dedicated inference machine available, service becomes reachable
- Actual result: port `30000` refused connections, and the only available SSH machine was already reporting live training
- Follow-up: provision or reserve a dedicated inference host before phase 7

### 8.1.1 Trainer Agent

- Status: `pass`
- Time: 2026-03-29 CST
- Commit: `ad1be41`
- Command: local `TrainerAgent.execute()` snippet
- Inputs / config: real `Experiment` object, no execution provider configured
- Machine / provider / image: local host
- Output artifact path: `n/a`
- Log path: `logs/real-tests/2026-03-29/MX-logs/8.1.1.log`
- Expected result: honest blocked, launched, or completed outcome without fake success
- Actual result: `TrainingOutcome(status='blocked', ..., reason='No execution provider configured')`
- Follow-up: rerun with a safe dedicated provider once one is available

### 8.3.1 Evolution Loop

- Status: `pass`
- Time: 2026-03-29 CST
- Commit: `ad1be41`
- Command: local `EvolutionLoop.step()` snippet
- Inputs / config: real strategist, trainer, data agent; real experiment tracker; live score dict
- Machine / provider / image: local host
- Output artifact path: `n/a`
- Log path: `logs/real-tests/2026-03-29/MX-logs/8.3.1.log`
- Expected result: honest blocked or launched or completed state, no scoreless fake-success path
- Actual result: `Step 1: status=blocked, target=NAVWORLD, geo_mean=0.00, improved=False`, reason `Experiment validation failed: ['No train_config specified']`
- Follow-up: use a real training config and a safe provider when moving from blocked-path validation to launched-path validation

## Blockers

- The only configured SSH machine, `m1`, reported active training, so image build and inference start were not run there to avoid disturbing live work.
- No live inference endpoint was available on `m1:30000`, so phase 7 eval runs could not proceed.
- Targon smoke launch for `train launch` still fails because generated workload names are not sanitized for Targon naming rules.

## Exit Judgment

- Applicable phases executed: 0, 1, 2, 3, 6 partial, 8 partial
- Required phases missing for full end-to-end closure: 4, 5 complete, 6 complete, 7, 9
- Milestone exit criteria supported by this report: no for any runtime-facing milestone that requires full training, inference, or evaluation real-chain proof
- Follow-up required before milestone closeout:
  - fix `forge data aggregate` CLI callback wiring
  - fix SWE sync error handling for SSH auth failures
  - fix remote sync/run directory upload fallback for Targon SSH deployments
  - reserve a safe dedicated machine for image build, training smoke, and inference smoke
  - sanitize Targon workload names in the `train launch` path
