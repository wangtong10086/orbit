# Real Test Plan

This file is the execution runbook for the active execution-plane refactor.

It is no longer enough to prove that `train` or `eval` commands work through the legacy control-side entrypoints. The active goal is to prove that the new execution plane can run bundles directly through `forge worker`.

## Scope

Run this plan when a change touches:

- `forge/control/`
- `forge control`
- `forge/execution/`
- `forge worker`
- bundle rendering
- Docker runtime behavior
- Targon runtime behavior
- SSH runtime behavior
- artifact collection

## Minimum acceptance for the execution-plane phase

The execution-plane phase is not complete until all of the following are true:

1. a train bundle can be rendered and validated locally
2. an eval bundle can be rendered and validated locally
3. a collect bundle can be rendered and validated locally
4. all three can run through Docker runtime
5. at least one train bundle can run through Targon runtime
6. at least one train bundle can run through SSH runtime
7. status, logs, and artifact collection all work through `forge worker`
8. control-plane CLI can create experiments and render or submit work without using deleted legacy command families
9. control-plane CLI can render eval and collect work and keep their run records separate from training

## Command Convention

Use:

```bash
uv run forge ...
```

Do not treat unrelated sidecar or historical command success as a substitute for execution-plane proof.

## Machine Policy

When SSH or inference validation requires a rental machine:

- do not default to the current `machines.json` inventory
- provision a new isolated machine for the test session
- only then register or reference it in the command log

## Report Requirement

Every real-test session must produce:

- a markdown report under `logs/real-tests/YYYY-MM-DD/`
- raw command logs under a sibling `*-logs/` directory
- artifact notes or copies under a sibling `*-artifacts/` directory

Valid per-item states:

- `pass`
- `fail`
- `blocked`
- `not_run`

## Phase A — Bundle Rendering

### A1 Train bundle

```bash
uv run forge worker render train tmp/train.jsonl --bundle-dir tmp/bundle-train --job-id train-smoke
uv run forge worker validate-bundle tmp/bundle-train
```

Pass criteria:

- bundle directory exists
- `job.json` exists
- `inputs/swift_config.yaml` exists
- `scripts/entrypoint.sh` exists

### A2 Eval bundle

```bash
uv run forge worker render eval --bundle-dir tmp/bundle-eval --job-id eval-smoke --model Qwen/Qwen2.5-0.5B-Instruct --envs GAME --samples 2
uv run forge worker validate-bundle tmp/bundle-eval
```

### A3 Collect bundle

```bash
uv run forge worker render collect-navworld --bundle-dir tmp/bundle-collect --job-id collect-smoke -n 1
uv run forge worker validate-bundle tmp/bundle-collect
```

## Phase B — Docker Runtime

### B1 Train via Docker

```bash
uv run forge worker run tmp/bundle-train --runtime docker --foreground --image <existing-dev-image>
uv run forge worker collect tmp/bundle-train
```

Pass criteria:

- command starts from the bundle entrypoint
- `artifacts/training.log` exists
- worker collect returns a manifest

### B2 Eval via Docker

```bash
uv run forge worker run tmp/bundle-eval --runtime docker --foreground --image <existing-dev-image>
uv run forge worker collect tmp/bundle-eval
```

Pass criteria:

- evaluation artifacts are written under the bundle `artifacts/` directory

### B3 Collect via Docker

```bash
uv run forge worker run tmp/bundle-collect --runtime docker --foreground --image <existing-dev-image>
uv run forge worker collect tmp/bundle-collect
```

Pass criteria:

- collection output file exists under the bundle `artifacts/` directory

## Phase C — SSH Runtime

### C1 Train via SSH

```bash
uv run forge worker run tmp/bundle-train --runtime ssh --target <isolated-machine>
uv run forge worker status tmp/bundle-train
uv run forge worker logs tmp/bundle-train --tail 50
uv run forge worker collect tmp/bundle-train
```

Pass criteria:

- remote run is accepted
- status returns a meaningful state
- logs are retrievable
- artifacts can be downloaded back into the local bundle

## Phase D — Targon Runtime

Current Targon validation target:

- explicit runtime: `targon`
- explicit profile: `rental`
- explicit target: a registered isolated rental machine
- optional staging acceleration: `HF_RUNTIME_REPO` + `HF_TOKEN`

If HF staging is not configured, the same checklist still applies; the runtime should fall back to direct SSH upload of the rendered project/bundle archives.

### D1 Train via Targon rental profile

```bash
uv run forge worker run tmp/bundle-train --runtime targon --target <isolated-machine> --profile rental --foreground --image <existing-dev-image>
uv run forge worker status tmp/bundle-train
uv run forge worker logs tmp/bundle-train --tail 50
uv run forge worker collect tmp/bundle-train
```

### D2 Train via Targon rental profile without HF staging

```bash
unset HF_RUNTIME_REPO HF_BACKUP_REPO HF_TOKEN
uv run forge worker run tmp/bundle-train --runtime targon --target <isolated-machine> --profile rental --image <existing-dev-image>
uv run forge worker status tmp/bundle-train
uv run forge worker logs tmp/bundle-train --tail 50
uv run forge worker collect tmp/bundle-train
```

Pass criteria:

- Targon run is accepted
- `--foreground` blocks until remote completion when requested
- logs are retrievable
- artifacts are collectable
- the run still works when HF staging is absent and SSH upload fallback is used

## Phase E — Regression

After any milestone that changes execution-plane code, rerun:

```bash
./.venv/bin/python -m pytest -q tests/test_execution.py tests/test_cli.py
./.venv/bin/python -m compileall forge/execution forge/cli_worker.py forge/cli.py
uv run forge --help
uv run forge worker --help
```

## Phase F — Control-Plane CLI Smoke

### F1 Control create and show

```bash
uv run forge control --dir tmp/control-smoke create --id v-smoke --variable improve_navworld --hypothesis smoke --train-config '{"model":"Qwen/Qwen3-32B","learning_rate":0.0001,"lora_rank":64,"max_length":4096,"num_train_epochs":1,"output_dir":"/tmp/checkpoints"}' --data-config '{"GAME":{"count":100}}'
uv run forge control --dir tmp/control-smoke show v-smoke --json
```

Pass criteria:

- experiment file is created under the requested directory
- `show --json` returns the same experiment id and metadata

### F2 Control render train

```bash
printf '{"messages":[]}\n' > tmp/control-smoke-train.jsonl
uv run forge control --dir tmp/control-smoke render-train v-smoke tmp/control-smoke-train.jsonl --bundle-dir tmp/control-bundle-smoke
```

Pass criteria:

- bundle is created
- experiment state records the bundle path under `results.training_run.bundle_path`

### F3 Control render eval and collect

```bash
uv run forge control --dir tmp/control-smoke render-eval v-smoke --model Qwen/Qwen2.5-0.5B-Instruct --envs GAME --bundle-dir tmp/control-bundle-eval
uv run forge control --dir tmp/control-smoke render-collect-navworld v-smoke -n 1 --bundle-dir tmp/control-bundle-collect
uv run forge control --dir tmp/control-smoke show v-smoke --json
```

Pass criteria:

- eval bundle is created
- collect bundle is created
- experiment state records:
  - `results.evaluation_run.bundle_path`
  - `results.collect_run.bundle_path`

### F4 Control-plane runtime control

```bash
uv run forge control --dir tmp/control-runtime-smoke create --id v-runtime-smoke --variable runtime_control --hypothesis 'control plane can drive targon runtime' --train-config '{"model":"Qwen/Qwen2.5-0.5B-Instruct","learning_rate":0.0001,"lora_rank":64,"max_length":1024,"num_train_epochs":1,"per_device_train_batch_size":1,"gradient_accumulation_steps":1,"num_gpus":1,"output_dir":"/tmp/checkpoints"}' --data-config '{"GAME":{"count":1}}'
printf '{"messages":[]}\n' > tmp/control-runtime-smoke/train.jsonl
uv run forge control --dir tmp/control-runtime-smoke submit-train v-runtime-smoke tmp/control-runtime-smoke/train.jsonl --runtime targon --target <isolated-machine> --profile rental --image <existing-dev-image> --gpu-type H200 --bundle-dir tmp/control-runtime-smoke/bundle-train
uv run forge control --dir tmp/control-runtime-smoke run-status v-runtime-smoke
uv run forge control --dir tmp/control-runtime-smoke run-logs v-runtime-smoke --tail 80
uv run forge control --dir tmp/control-runtime-smoke terminate-run v-runtime-smoke
uv run forge control --dir tmp/control-runtime-smoke show v-runtime-smoke --json
```

Pass criteria:

- control-plane submit returns a real run id
- follow-up control commands work without repeating `--runtime`
- status returns a meaningful remote state
- logs return real remote output
- terminate updates the experiment record to `terminated`

### F5 Control-plane non-train runtime control

```bash
uv run forge control --dir tmp/control-final-smoke create --id v-collect-final --variable runtime_control_collect --hypothesis 'control plane collect smoke' --train-config '{"model":"Qwen/Qwen2.5-0.5B-Instruct","learning_rate":0.0001,"lora_rank":64,"max_length":1024,"num_train_epochs":1,"per_device_train_batch_size":1,"gradient_accumulation_steps":1,"num_gpus":1,"output_dir":"/tmp/checkpoints"}' --data-config '{"GAME":{"count":1}}'
uv run forge control --dir tmp/control-final-smoke submit-collect-navworld v-collect-final --runtime targon --target <isolated-machine> -n 1 --profile rental --image <existing-dev-image> --gpu-type H200 --bundle-dir tmp/control-final-smoke/bundle-collect
uv run forge control --dir tmp/control-final-smoke run-status v-collect-final --task collect
uv run forge control --dir tmp/control-final-smoke run-logs v-collect-final --task collect --tail 60
uv run forge control --dir tmp/control-final-smoke terminate-run v-collect-final --task collect
uv run forge control --dir tmp/control-final-smoke show v-collect-final --json
```

Pass criteria:

- collect submit returns a real run id
- follow-up commands work without repeating `--runtime`
- state and logs come from the real remote run
- `results.collect_run.*` is updated
- top-level `experiment.status` is not overwritten by the collect lifecycle
