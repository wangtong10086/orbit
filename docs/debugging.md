# Debugging Guide

This guide is the entrypoint for debugging ORBIT runs. Use it to decide where to
look first, which log surface answers which question, and which deeper tutorial
to read next.

The primary documented operating model is still:

- run the control plane locally
- submit work through an execution template
- execute the bundle on a Targon rental
- collect logs and artifacts after the run

For local-only bundle debugging, use the same log surfaces, but run the bundle
through `python3 -m orbit worker ...` instead of the control-plane flow.

## Debugging Mental Model

Think about debugging as three separate layers:

- control-plane state
  - experiment metadata, run records, template selection, and collected manifest
- execution-plane audit
  - remote staging, launch, status probes, collection, and termination
- task/runtime output
  - precheck output, training output, metrics logs, and optional GPU memory audit

In bundle terms:

- `runtime/runtime.log`
  - execution-plane audit trail for all worker paths
- task-specific files under `artifacts/`
  - task output logs and task artifacts
- training bundles may additionally write:
  - `artifacts/runtime-precheck.log`
  - `artifacts/training.log`
  - `artifacts/checkpoints/*/logging.jsonl`
- GPU training bundles may additionally write:
  - `artifacts/nvml-audit.jsonl`
  - `artifacts/nvml-audit.log`

## Where To Look First

Use this table when you do not yet know where the failure lives.

| Symptom | First files to inspect | What they answer |
| --- | --- | --- |
| Submit, stage, collect, or terminate behavior looks wrong | `runtime/runtime.log` | Whether the execution plane staged, launched, probed, collected, or terminated the bundle correctly |
| Training bundle starts but fails before real training begins | `artifacts/runtime-precheck.log`, `runtime/runtime.log` | Whether imports, staged packages, and runtime prerequisites resolved before launch |
| Training crashed or stalled | task-specific logs under `artifacts/`, then `artifacts/training.log` if present | What the task runtime printed and where it stopped |
| Training metrics look wrong or training is not progressing | `artifacts/checkpoints/*/logging.jsonl`, `artifacts/training.log` | Whether steps, losses, and task-specific metrics are moving |
| GPU memory/OOM issue on a GPU training bundle | `artifacts/training.log`, `artifacts/nvml-audit.jsonl`, `artifacts/nvml-audit.log` | Whether memory pressure came from the training process, another process, or environment drift |
| Config or input validation failed before launch | CLI traceback plus the relevant schema module | Whether the failure was a contract/schema problem rather than a runtime/logging problem |

## Log Surfaces

At the entrypoint level, the surfaces split like this:

| Surface | Typical path | Owned by | Use it for |
| --- | --- | --- | --- |
| Runtime audit log | `runtime/runtime.log` | execution plane | staging, launch, status, collect, terminate, remote orchestration |
| Task logs | `artifacts/*.log` | task runtime | task-specific stdout, stderr, progress, and failures |
| Training precheck + metrics | training-bundle paths under `artifacts/` | training bundle/runtime | import checks, training progress, and metrics |
| NVML audit files | training-bundle paths under `artifacts/` | NVML audit helper | GPU memory usage, GPU utilization, per-process memory snapshots |

Important terminology rule:

- `logging.jsonl` is a training metrics log
- it is not a "Pydantic log"
- Pydantic in this repository is used for contracts, schema validation, and
  input normalization

## Tutorials

Read these in order if you are new to the repository:

1. [logging-and-artifacts.md](logging-and-artifacts.md)
2. [nvml-gpu-audit.md](nvml-gpu-audit.md) when debugging GPU memory or OOM
3. [pydantic-validation.md](pydantic-validation.md) when a failure happens
   during config parsing or contract validation

Reference docs that stay authoritative for command behavior and runbook commands:

- [cli.md](cli.md)
- [operations.md](operations.md)
- [test-runbook.md](test-runbook.md)

## Common Workflows

### Debug a remote run after collection

1. Run `python3 -m orbit control run collect <exp-id> <run-key>`.
2. Locate the local bundle path:
   - if you submitted with `--bundle-dir`, use that directory
   - otherwise inspect the collect result or experiment record to find the local
     bundle/artifact destination before opening files
3. Inspect `runtime/runtime.log` first if you suspect staging, launch, or
   collection issues.
4. Inspect task-specific files under `artifacts/`.
5. If this is a training bundle, then inspect `artifacts/runtime-precheck.log`,
   `artifacts/training.log`, and `artifacts/checkpoints/*/logging.jsonl` as
   needed.

### Debug a bundle locally

1. Run `python3 -m orbit worker run <bundle-dir> --placement local --launch-mode host_process --foreground`.
2. Run `python3 -m orbit worker collect <bundle-dir>`.
3. Start with `runtime/runtime.log`.
4. Then inspect task-specific files under `artifacts/`.
5. If this is a training bundle, continue to `runtime-precheck.log`,
   `training.log`, and `logging.jsonl`.

### Debug a GPU memory issue

1. Search `artifacts/training.log` for `OOM`, `OutOfMemory`, `CUDA`, or
   `Traceback`.
2. Open `artifacts/nvml-audit.jsonl` to confirm whether total GPU usage was
   already high before the failure.
3. Correlate the last NVML sample with the last useful line in
   `artifacts/training.log`.
4. If another PID owns a large share of memory, debug the machine state, not the
   ORBIT training config alone.

## Troubleshooting Map

Use these shortcuts before escalating into deeper code inspection:

- "Remote launch failed before training"
  - read `runtime/runtime.log`
  - then read task-specific `artifacts/*.log`
  - for training bundles, then read `artifacts/runtime-precheck.log`
- "Training started, then crashed"
  - read `artifacts/training.log`
  - then read `artifacts/checkpoints/*/logging.jsonl`
- "OOM or GPU utilization looks wrong"
  - read `artifacts/nvml-audit.jsonl`
  - then read [nvml-gpu-audit.md](nvml-gpu-audit.md)
- "Validation error mentions fields, schema, or type conversion"
  - read [pydantic-validation.md](pydantic-validation.md)
