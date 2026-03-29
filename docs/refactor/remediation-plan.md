# Active Remediation Plan

This document tracks the remaining architecture-alignment repairs for the active
control-plane / execution-plane refactor.

It replaces older remediation notes that were written against deleted command
families and older execution paths.

## Completion Rule

A remediation item is complete only when all of the following are true:

1. the code fix is in place
2. the original failing or risky path is rerun
3. the rerun path passes
4. at least one downstream dependent path also passes
5. the rerun result is recorded in `docs/refactor/progress.md`

## Priority Summary

### P0 — Must fix before claiming architecture alignment

- experiment top-level status only tracks the training lifecycle
- `ControlPlane` old training-only wrapper API is removed
- agents stop carrying runtime backend and runtime flags
- active docs stop describing removed provider and legacy command models

### P1 — Must fix before claiming old API removal is complete

- compatibility environment registry removal
- old training aliases removal
- compatibility CLI wrapper removal

## Repair Checklist

### R1 — Make `Experiment.status` training-only

Required fix:

- `evaluation_run` and `collect_run` must not overwrite top-level experiment status
- top-level `status` updates only on train lifecycle transitions

Self-test steps:

```bash
./.venv/bin/python -m pytest -q tests/test_control.py
```

Pass criteria:

- submitting or rendering eval/collect leaves top-level training status unchanged
- train status transitions still work

### R2 — Remove training-only wrapper methods from `ControlPlane`

Required fix:

- remove training-specific status/log/collect/terminate wrappers
- keep only the generic run-control API keyed by `train|eval|collect`

Self-test steps:

```bash
rg -n "refresh_training_status|collect_training_artifacts|read_training_logs|terminate_training" forge tests docs
./.venv/bin/python -m pytest -q tests/test_control.py tests/test_cli.py
```

Pass criteria:

- the `rg` command returns no active references
- control-plane tests pass

### R3 — Move agent runtime decisions into the control plane

Required fix:

- `TrainerAgent` no longer accepts runtime backend or runtime flags
- agent submits through `ControlPlane` using a submission target resolver

Self-test steps:

```bash
rg -n "runtime_backend|runtime_target|runtime_profile|runtime_image|runtime_gpu_type|runtime_dataset_repo" forge/agent tests/test_agent.py
./.venv/bin/python -m pytest -q tests/test_agent.py tests/test_control.py
```

Pass criteria:

- no active agent code uses the removed runtime fields
- agent tests pass

### R4 — Remove environment registry compatibility surfaces

Required fix:

- remove `EnvRegistry` and `EnvHub`
- move environment tests and active imports to `default_environment_catalog()`

Self-test steps:

```bash
rg -n "EnvRegistry|EnvHub" forge tests docs
./.venv/bin/python -m pytest -q tests/test_env.py
```

Pass criteria:

- no active references remain
- environment tests pass

### R5 — Remove training aliases and old helper exports

Required fix:

- remove `TrainConfig`
- remove `SftBackend`
- stop documenting or testing those names

Self-test steps:

```bash
rg -n "TrainConfig|SftBackend" forge tests docs
./.venv/bin/python -m pytest -q tests/test_training.py
```

Pass criteria:

- no active references remain
- training tests pass

### R6 — Real control-plane train smoke

Required fix or verification:

- prove the control plane can create, submit, inspect, and terminate a real Targon training run
- follow-up commands must infer runtime from the recorded run handle

Self-test steps:

```bash
uv run forge control --dir tmp/control-runtime-smoke create --id v-runtime-smoke --variable runtime_control --hypothesis 'control plane can drive targon runtime' --train-config '{"model":"Qwen/Qwen2.5-0.5B-Instruct","learning_rate":0.0001,"lora_rank":64,"max_length":1024,"num_train_epochs":1,"per_device_train_batch_size":1,"gradient_accumulation_steps":1,"num_gpus":1,"output_dir":"/tmp/checkpoints"}' --data-config '{"GAME":{"count":1}}'
printf '{"messages":[]}\n' > tmp/control-runtime-smoke/train.jsonl
uv run forge control --dir tmp/control-runtime-smoke submit-train v-runtime-smoke tmp/control-runtime-smoke/train.jsonl --runtime targon --profile bootstrap --dataset-repo <repo> --gpu-type H200 --bundle-dir tmp/control-runtime-smoke/bundle-train
uv run forge control --dir tmp/control-runtime-smoke run-status v-runtime-smoke
uv run forge control --dir tmp/control-runtime-smoke run-logs v-runtime-smoke --tail 80
uv run forge control --dir tmp/control-runtime-smoke terminate-run v-runtime-smoke
uv run forge control --dir tmp/control-runtime-smoke show v-runtime-smoke --json
```

Pass criteria:

- control-plane submit returns a real run id
- follow-up commands work without repeating `--runtime`
- status returns a meaningful remote state
- logs return real remote output
- terminate updates the experiment record to `terminated`

## Closure Checklist

The current remediation pass is complete only when:

- [ ] R1 passed
- [ ] R2 passed
- [ ] R3 passed
- [ ] R4 passed
- [ ] R5 passed
- [ ] R6 passed

Do not mark the active refactor phases complete until the applicable items
above are rerun and recorded in `docs/refactor/progress.md`.
