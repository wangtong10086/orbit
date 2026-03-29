# Real Test Report

- Date: 2026-03-29
- Operator: Codex
- Milestone: Post-audit remediation follow-up for reopened M3 and M6 runtime failures
- Scope: R1-R9 reruns plus final real eval and honest vertical-slice closeout on isolated Targon rentals
- Git commit: `ad1be41` with local remediation changes in the working tree
- Branch: `refactor/three-layer-architecture`
- Environment: local workstation plus connected Targon SSH and serverless resources
- Provider(s): local filesystem, local Docker `affinetes` eval, SSH backend, Targon bootstrap provider, Targon image provider, isolated Targon rentals, dedicated sglang runtime sidecar
- Machine(s): local host, `m1` (`wrk-omej9xgvjoia@ssh.deployments.targon.com`), `r5-rental` (`wrk-hld5pe947nrl`, `72.46.85.157:32193`), `r7-rental` (`wrk-t6ws8521sk2h`, `72.46.85.157:32684`)
- Image(s): `pytorch/pytorch:2.5.1-cuda12.4-cudnn9-devel`, `wangtong123/affine-forge:latest`
- Overall result: pass

## Summary

| Test ID | Status | Command | Artifact Path | Log Path | Notes |
|---|---|---|---|---|---|
| 0.2.2 | pass | `./.venv/bin/pytest -q` | `n/a` | `logs/real-tests/2026-03-29/MX-remediation-logs/R9-pytest-full.log` | 200 tests passed |
| R1.1 | pass | `./.venv/bin/python -m forge data aggregate --envs GAME,NAVWORLD -o tmp/train_smoke.jsonl --no-upload` | `tmp/train_smoke.jsonl` | `logs/real-tests/2026-03-29/MX-remediation-logs/R1-aggregate.log` | original failing command now succeeds |
| R1.2 | pass | `./.venv/bin/python - <<'PY' ... validate tmp/train_smoke.jsonl ...` | `tmp/train_smoke.jsonl` | `logs/real-tests/2026-03-29/MX-remediation-logs/R1-validate.log` | downstream validation confirmed packed `messages` |
| R2.1 | pass | `./.venv/bin/python -m forge data swe-sync --dry-run` | `n/a` | `logs/real-tests/2026-03-29/MX-remediation-logs/R2-swe-sync.log` | now exits with explicit blocker instead of traceback |
| R2.2 | pass | `./.venv/bin/python -m forge data swe-status` | `n/a` | `logs/real-tests/2026-03-29/MX-remediation-logs/R2-swe-status.log` | downstream command reports blocked remote state honestly |
| R3.1 | pass | `./.venv/bin/python -m forge remote machine -m m1 sync` | remote `/root/project/*` | `logs/real-tests/2026-03-29/MX-remediation-logs/R3-sync.log` | directory-capable fallback completed |
| R3.2 | pass | `./.venv/bin/python -m forge remote machine -m m1 run "pwd"` | remote `/root/project` | `logs/real-tests/2026-03-29/MX-remediation-logs/R3-run.log` | downstream run succeeded after sync |
| R3.3 | pass | `./.venv/bin/python -m forge remote machine -m m1 exec 'test -d /root/project/forge && echo ok'` | remote `/root/project/forge` | `logs/real-tests/2026-03-29/MX-remediation-logs/R3-verify.log` | remote tree exists |
| R4.1 | pass | `./.venv/bin/python -m forge train launch tmp/game_train.jsonl --provider targon-bootstrap --model Qwen/Qwen2.5-0.5B-Instruct --epochs 1 --batch-size 1` | Targon run `wrk-ak2wx7hqyt6m` | `logs/real-tests/2026-03-29/MX-remediation-logs/R4-bootstrap-launch.log` | original failing command accepted after workload-name sanitization |
| R4.2 | pass | `./.venv/bin/python -m forge remote compute logs wrk-ak2wx7hqyt6m --tail 50` | Targon run `wrk-ak2wx7hqyt6m` | `logs/real-tests/2026-03-29/MX-remediation-logs/R4-bootstrap-logs.log` | bootstrap logs readable |
| R4.3 | pass | `./.venv/bin/python -m forge train launch tmp/game_train.jsonl --provider targon-image --image wangtong123/affine-forge:latest --model Qwen/Qwen2.5-0.5B-Instruct --epochs 1 --batch-size 1` | Targon run `wrk-mgypk092zlit` | `logs/real-tests/2026-03-29/MX-remediation-logs/R4-image-launch.log` | original failing command accepted after workload-name sanitization |
| R4.4 | pass | `./.venv/bin/python -m forge remote compute logs wrk-mgypk092zlit --tail 50` | Targon run `wrk-mgypk092zlit` | `logs/real-tests/2026-03-29/MX-remediation-logs/R4-image-logs.log` | image-provider logs readable |
| R4.5 | pass | `./.venv/bin/python -m forge remote compute list` | `n/a` | `logs/real-tests/2026-03-29/MX-remediation-logs/R4-compute-list-after-image.log` | both workloads visible simultaneously |
| R4.6 | pass | `./.venv/bin/python -m forge remote compute terminate <run_id>` | `n/a` | `logs/real-tests/2026-03-29/MX-remediation-logs/R4-bootstrap-terminate.log`, `logs/real-tests/2026-03-29/MX-remediation-logs/R4-image-terminate.log` | cleanup completed |
| R5.0 | pass | `POST /tha/v2/workloads` + `POST /tha/v2/workloads/wrk-hld5pe947nrl/deploy` | workload `wrk-hld5pe947nrl` | `logs/real-tests/2026-03-29/MX-remediation-artifacts/r5_r9/rental-create-dropbear-response.json`, `logs/real-tests/2026-03-29/MX-remediation-artifacts/r5_r9/rental-deploy-dropbear.json` | new isolated rental created with direct SSH/inference ports |
| R5.1 | pass | `ssh -i ~/.ssh/affine_rental -p 32193 root@72.46.85.157 'echo ok && whoami && hostname && nvidia-smi -L'` | `n/a` | `logs/real-tests/2026-03-29/MX-remediation-logs/R5-rental-dropbear-ssh.log` | isolated rental accepts SSH and exposes GPU |
| R5.2 | pass | `./.venv/bin/python -m forge remote machine register r5-rental 72.46.85.157 --port 32193 --user root --key ~/.ssh/affine_rental --gpu-type RTX4090` | `machines.json` | `logs/real-tests/2026-03-29/MX-remediation-logs/R5-machine-register.log` | validation machine registered explicitly for this session |
| R5.3 | pass | `./.venv/bin/python -m forge remote machine -m r5-rental bootstrap --training-only` | remote `/data/.affine` | `logs/real-tests/2026-03-29/MX-remediation-logs/R5-bootstrap.log` | training stack bootstrapped and verified on isolated rental |
| R5.4 | pass | `./.venv/bin/python -m forge train launch tmp/game_train.jsonl --provider ssh --host 72.46.85.157 --port 32193 --user root --key ~/.ssh/affine_rental --model Qwen/Qwen2.5-0.5B-Instruct --epochs 1 --batch-size 1 --max-length 1024` | remote run `72.46.85.157` | `logs/real-tests/2026-03-29/MX-remediation-logs/R5-ssh-launch-rerun.log` | original SSH launch command now submits successfully |
| R5.5 | pass | `./.venv/bin/python -m forge remote machine -m r5-rental exec 'sed -n "1,120p" /root/training.log'` | `/root/data/game_train.jsonl`, `/root/training.log` | `logs/real-tests/2026-03-29/MX-remediation-logs/R5-training-tail-2.log` | downstream check proved dataset upload and live `swift` training start |
| R6.0 | pass | `./.venv/bin/python -m forge remote machine -m r5-rental start-sglang Qwen/Qwen2.5-0.5B-Instruct --tp 1 --wait` | remote `screen` + `/root/logs/sglang.log` | `logs/real-tests/2026-03-29/MX-remediation-logs/R6-start-sglang-rerun-4.log` | dedicated sglang runtime now starts successfully on isolated rental |
| R6.1 | pass | `curl -sS --max-time 10 http://72.46.85.157:31160/v1/models` | inference endpoint `http://72.46.85.157:31160/v1` | `logs/real-tests/2026-03-29/MX-remediation-logs/R6-direct-models.log` | direct endpoint reachable from local workstation |
| R7.0 | pass | `./.venv/bin/python -m forge eval run --model Qwen/Qwen2.5-0.5B-Instruct --envs GAME --samples 2 --base-url http://72.46.85.157:32721/v1 --output-dir tmp/eval_smoke` | `tmp/eval_smoke/eval_summary.json`, `tmp/eval_smoke/eval_game.json` | `logs/real-tests/2026-03-29/MX-remediation-logs/R7-eval-game-pass-5.log` | original failing command now produces real GAME eval artifacts with completeness 100% |
| R8.0 | pass | `./.venv/bin/python -m forge eval run --model Qwen/Qwen2.5-0.5B-Instruct --envs GAME,NAVWORLD --samples 2 --base-url http://72.46.85.157:32721/v1 --output-dir tmp/eval_multi_smoke` | `tmp/eval_multi_smoke/eval_summary.json`, `tmp/eval_multi_smoke/eval_game.json`, `tmp/eval_multi_smoke/eval_navworld.json` | `logs/real-tests/2026-03-29/MX-remediation-logs/R8-eval-multi-pass-2.log` | multi-env eval now completes with real artifacts for both environments |
| R9.0 | pass | `forge data aggregate` -> `forge train launch` -> `forge remote machine start-sglang` -> `forge eval run` | `tmp/r9_train_smoke.jsonl`, `tmp/r9_eval_smoke/eval_summary.json` | `logs/real-tests/2026-03-29/MX-remediation-logs/R9-aggregate.log`, `logs/real-tests/2026-03-29/MX-remediation-logs/R9-train-launch.log`, `logs/real-tests/2026-03-29/MX-remediation-logs/R9-start-sglang.log`, `logs/real-tests/2026-03-29/MX-remediation-logs/R9-eval.log` | one honest vertical slice completed end-to-end on live resources |

## Detailed Entries

### R1 Dataset aggregate CLI rerun

- Status: `pass`
- Command:
  - `./.venv/bin/python -m forge data aggregate --envs GAME,NAVWORLD -o tmp/train_smoke.jsonl --no-upload`
  - `./.venv/bin/python - <<'PY' ... validate tmp/train_smoke.jsonl ...`
- Machine / provider / image: local host
- Output artifact path: `tmp/train_smoke.jsonl`
- Log path:
  - `logs/real-tests/2026-03-29/MX-remediation-logs/R1-aggregate.log`
  - `logs/real-tests/2026-03-29/MX-remediation-logs/R1-validate.log`
- Actual result:
  - aggregate command returned success
  - downstream validation printed `ok 3`
- Follow-up: none for R1

### R2 SWE sync infrastructure handling rerun

- Status: `pass`
- Command:
  - `./.venv/bin/python -m forge data swe-sync --dry-run`
  - `./.venv/bin/python -m forge data swe-status`
- Machine / provider / image: local host plus SSH attempt to `wrk-2g5l02247zvp@ssh.deployments.targon.com`
- Output artifact path: `n/a`
- Log path:
  - `logs/real-tests/2026-03-29/MX-remediation-logs/R2-swe-sync.log`
  - `logs/real-tests/2026-03-29/MX-remediation-logs/R2-swe-status.log`
- Actual result:
  - original command no longer crashes with `ValueError`
  - CLI now reports `Error: SWE sync blocked: ... Permission denied (publickey).`
  - downstream status command reports `[BLOCKED] ... Permission denied (publickey).`
- Follow-up: remote credentials still need to be fixed before SWE sync can complete, but the runtime failure mode is now stable and user-readable

### R3 Remote sync and run fallback rerun

- Status: `pass`
- Command:
  - `./.venv/bin/python -m forge remote machine -m m1 sync`
  - `./.venv/bin/python -m forge remote machine -m m1 run "pwd"`
  - `./.venv/bin/python -m forge remote machine -m m1 exec 'test -d /root/project/forge && echo ok'`
- Machine / provider / image: SSH backend to `m1`
- Output artifact path: remote `/root/project/`
- Log path:
  - `logs/real-tests/2026-03-29/MX-remediation-logs/R3-sync.log`
  - `logs/real-tests/2026-03-29/MX-remediation-logs/R3-run.log`
  - `logs/real-tests/2026-03-29/MX-remediation-logs/R3-verify.log`
- Actual result:
  - sync completed across directory paths that previously failed
  - downstream `run "pwd"` printed `/root/project`
  - remote `forge/` directory existence check returned `ok`
- Follow-up: none for R3

### R4 Targon launch rerun

- Status: `pass`
- Command:
  - `./.venv/bin/python -m forge train launch tmp/game_train.jsonl --provider targon-bootstrap --model Qwen/Qwen2.5-0.5B-Instruct --epochs 1 --batch-size 1`
  - `./.venv/bin/python -m forge train launch tmp/game_train.jsonl --provider targon-image --image wangtong123/affine-forge:latest --model Qwen/Qwen2.5-0.5B-Instruct --epochs 1 --batch-size 1`
  - `./.venv/bin/python -m forge remote compute list`
  - `./.venv/bin/python -m forge remote compute logs wrk-ak2wx7hqyt6m --tail 50`
  - `./.venv/bin/python -m forge remote compute logs wrk-mgypk092zlit --tail 50`
  - `./.venv/bin/python -m forge remote compute terminate wrk-ak2wx7hqyt6m`
  - `./.venv/bin/python -m forge remote compute terminate wrk-mgypk092zlit`
- Machine / provider / image: Targon bootstrap provider and Targon image provider
- Output artifact path:
  - bootstrap run `wrk-ak2wx7hqyt6m`
  - image run `wrk-mgypk092zlit`
- Log path:
  - `logs/real-tests/2026-03-29/MX-remediation-logs/R4-bootstrap-launch.log`
  - `logs/real-tests/2026-03-29/MX-remediation-logs/R4-image-launch.log`
  - `logs/real-tests/2026-03-29/MX-remediation-logs/R4-compute-list-after-image.log`
  - `logs/real-tests/2026-03-29/MX-remediation-logs/R4-bootstrap-logs.log`
  - `logs/real-tests/2026-03-29/MX-remediation-logs/R4-image-logs.log`
  - `logs/real-tests/2026-03-29/MX-remediation-logs/R4-bootstrap-terminate.log`
  - `logs/real-tests/2026-03-29/MX-remediation-logs/R4-image-terminate.log`
- Actual result:
  - both original launch commands were accepted by Targon
  - `compute list` showed both workloads live at the same time
  - bootstrap logs showed runtime startup and ms-swift installation
  - image logs showed the generated `swift sft` command being executed
  - both test workloads were terminated successfully after verification
- Follow-up: none for R4

### R5 SSH provider dataset handling

- Status: `pass`
- Command:
  - `POST https://api.targon.com/tha/v2/workloads` with `logs/real-tests/2026-03-29/MX-remediation-artifacts/r5_r9/rental-create-dropbear.json`
  - `POST https://api.targon.com/tha/v2/workloads/wrk-hld5pe947nrl/deploy`
  - `ssh -o StrictHostKeyChecking=no -i ~/.ssh/affine_rental -p 32193 root@72.46.85.157 'echo ok && whoami && hostname && nvidia-smi -L'`
  - `./.venv/bin/python -m forge remote machine register r5-rental 72.46.85.157 --port 32193 --user root --key ~/.ssh/affine_rental --gpu-type RTX4090`
  - `./.venv/bin/python -m forge remote machine -m r5-rental bootstrap --training-only`
  - `./.venv/bin/python -m forge train launch tmp/game_train.jsonl --provider ssh --host 72.46.85.157 --port 32193 --user root --key ~/.ssh/affine_rental --model Qwen/Qwen2.5-0.5B-Instruct --epochs 1 --batch-size 1 --max-length 1024`
  - `./.venv/bin/python -m forge remote machine -m r5-rental exec 'ls -lh /root/data/game_train.jsonl /root/scripts/swift_config.yaml /root/training.log && sed -n "1,120p" /root/training.log'`
- Machine / provider / image:
  - isolated rental `wrk-hld5pe947nrl`
  - registered machine `r5-rental`
  - image `pytorch/pytorch:2.5.1-cuda12.4-cudnn9-devel`
- Output artifact path:
  - `logs/real-tests/2026-03-29/MX-remediation-artifacts/r5_r9/rental-create-dropbear-response.json`
  - `logs/real-tests/2026-03-29/MX-remediation-artifacts/r5_r9/rental-deploy-dropbear.json`
  - remote `/root/data/game_train.jsonl`
  - remote `/root/training.log`
- Log path:
  - `logs/real-tests/2026-03-29/MX-remediation-logs/R5-rental-dropbear-ssh.log`
  - `logs/real-tests/2026-03-29/MX-remediation-logs/R5-machine-register.log`
  - `logs/real-tests/2026-03-29/MX-remediation-logs/R5-bootstrap.log`
  - `logs/real-tests/2026-03-29/MX-remediation-logs/R5-ssh-launch-rerun.log`
  - `logs/real-tests/2026-03-29/MX-remediation-logs/R5-training-tail-2.log`
- Actual result:
  - the remediation run provisioned a fresh SSH-usable isolated rental instead of reusing `machines.json`
  - the original SSH launch command now succeeds against that rental
  - downstream evidence shows `/root/data/game_train.jsonl` was uploaded and `swift` started reading it on the remote side
- Follow-up: none for R5

### R6 Dedicated inference machine

- Status: `pass`
- Command:
  - `./.venv/bin/python -m forge remote machine -m r5-rental kill training`
  - `./.venv/bin/python -m forge remote machine -m r5-rental start-sglang Qwen/Qwen2.5-0.5B-Instruct --tp 1 --wait`
  - `curl -sS --max-time 10 http://72.46.85.157:31160/v1/models`
- Machine / provider / image:
  - isolated rental `r5-rental`
  - dedicated sidecar runtime `/data/.affine/sglang-venv`
- Output artifact path:
  - remote `/root/logs/sglang.log`
- Log path:
  - `logs/real-tests/2026-03-29/MX-remediation-logs/R6-kill-training.log`
  - `logs/real-tests/2026-03-29/MX-remediation-logs/R6-start-sglang-rerun-4.log`
  - `logs/real-tests/2026-03-29/MX-remediation-logs/R6-direct-models.log`
- Actual result:
  - the isolated rental was safely repurposed from training smoke to inference smoke
  - `remote machine start-sglang` now self-prepares a dedicated sglang runtime and reaches ready state
  - the direct inference endpoint responds from the local workstation
- Follow-up: keep the rental alive only until the remaining validation or cleanup is finished

### R7-R9 completion addendum

- Status: `pass`
- Additional fixes applied after Docker access was enabled:
  - local eval subprocesses now mirror proxy env vars across lower/upper-case names so child tools and Docker builds see the same host proxy settings
  - `scripts/eval_envs.py` now passes host proxy build args into `affinetes` image builds
  - `affinetes` image builds now use host networking when the configured proxy points at localhost, keeping the workstation proxy reachable during `docker build`
  - bridge-mode eval startup now cleans up partially created containers before retrying with single-replica host-network mode
  - NAVWORLD eval now maps `AMAP_API_KEY` to `AMAP_MAPS_API_KEY` so the real QQR tool server receives the expected credential
- R7 single-env rerun:
  - command: `./.venv/bin/python -m forge eval run --model Qwen/Qwen2.5-0.5B-Instruct --envs GAME --samples 2 --base-url http://72.46.85.157:32721/v1 --output-dir tmp/eval_smoke`
  - output artifacts:
    - `tmp/eval_smoke/eval_summary.json`
    - `tmp/eval_smoke/eval_game.json`
    - `tmp/eval_smoke/eval_game_incremental.jsonl`
  - log path:
    - `logs/real-tests/2026-03-29/MX-remediation-logs/R7-eval-game-pass-5.log`
  - result:
    - GAME eval completed with `mean_score=0.5`, `errors=0`, `samples=2`
- R8 multi-env rerun:
  - command: `./.venv/bin/python -m forge eval run --model Qwen/Qwen2.5-0.5B-Instruct --envs GAME,NAVWORLD --samples 2 --base-url http://72.46.85.157:32721/v1 --output-dir tmp/eval_multi_smoke`
  - output artifacts:
    - `tmp/eval_multi_smoke/eval_summary.json`
    - `tmp/eval_multi_smoke/eval_game.json`
    - `tmp/eval_multi_smoke/eval_navworld.json`
    - `tmp/eval_multi_smoke/eval_game_incremental.jsonl`
    - `tmp/eval_multi_smoke/eval_navworld_incremental.jsonl`
  - log path:
    - `logs/real-tests/2026-03-29/MX-remediation-logs/R8-eval-multi-pass-2.log`
  - result:
    - GAME completed with `mean_score=0.5`, `errors=0`, `samples=2`
    - NAVWORLD completed with `mean_score=0.0001`, `errors=0`, `samples=2`
- R9 honest vertical slice:
  - commands:
    - `./.venv/bin/python -m forge data aggregate --envs GAME,NAVWORLD --max-per-env 1 -o tmp/r9_train_smoke.jsonl --remote-name r9_train_smoke.jsonl`
    - `./.venv/bin/python -m forge train launch r9_train_smoke.jsonl --provider targon-bootstrap --dataset-repo monokoco/affine-sft-data --model Qwen/Qwen2.5-0.5B-Instruct --epochs 1 --batch-size 1 --max-length 1024`
    - `./.venv/bin/python -m forge remote machine -m r7-rental start-sglang Qwen/Qwen2.5-0.5B-Instruct --tp 1 --wait`
    - `./.venv/bin/python -m forge eval run --model Qwen/Qwen2.5-0.5B-Instruct --envs GAME --samples 2 --base-url http://72.46.85.157:32721/v1 --output-dir tmp/r9_eval_smoke`
  - input data source:
    - local canonical repositories for `GAME` and `NAVWORLD`
  - training dataset path:
    - local `tmp/r9_train_smoke.jsonl`
    - uploaded HF dataset file `monokoco/affine-sft-data:r9_train_smoke.jsonl`
  - training run ID:
    - `wrk-bb03wxp7m0l6`
  - inference endpoint:
    - `http://72.46.85.157:32721/v1`
  - evaluation output directory:
    - `tmp/r9_eval_smoke`
  - supporting log paths:
    - `logs/real-tests/2026-03-29/MX-remediation-logs/R9-aggregate.log`
    - `logs/real-tests/2026-03-29/MX-remediation-logs/R9-train-launch.log`
    - `logs/real-tests/2026-03-29/MX-remediation-logs/R9-start-sglang.log`
    - `logs/real-tests/2026-03-29/MX-remediation-logs/R9-eval.log`
    - `logs/real-tests/2026-03-29/MX-remediation-logs/R9-train-terminate.log`
    - `logs/real-tests/2026-03-29/MX-remediation-logs/R9-rental-terminate.log`
  - result:
    - the slice completed with real data generation, real dataset upload, real training launch, real inference startup, and real eval artifact production
    - final GAME eval completed with `mean_score=0.5`, `errors=0`, `samples=2`
    - both temporary workloads were terminated after verification

## Blockers

- None for runtime remediation closeout.

## Exit Judgment

- Applicable remediation items executed: R1, R2, R3, R4, R5, R6, R7, R8, R9
- Required remediation items still blocked: none
- Original failing commands rerun and recorded: yes for R1-R8, plus a real R9 vertical slice
- At least one downstream dependent command rerun and recorded: yes for every applicable remediation item
- Regression suite rerun after latest code changes: yes, `200 passed`
- Milestone exit criteria fully supported by this report: yes for the runtime remediation checklist
- Follow-up required before overall roadmap closeout:
  - keep the reopened M3/M6 architectural cleanup work separate from this now-complete runtime remediation pass
