# Logging and Artifacts Guide

This guide explains the log and artifact surfaces that appear inside an ORBIT
bundle. Read this first if you want a practical map of what to inspect after a
run or during local bundle debugging.

## First Locate The Bundle

The paths in this guide are bundle-relative paths, not global repository paths.

Before reading any file, first locate the local bundle directory:

- if the command used `--bundle-dir`, use that directory
- if you ran `orbit control run collect`, inspect the collect result or the
  experiment record to find the local artifact destination
- if you only used `run logs` and have not collected artifacts yet, you may not
  have the full local `artifacts/` tree yet

## Bundle Layout

The execution plane hands work to the runtime as a bundle. The directories that
matter most for debugging are:

- `artifacts/`
  - task logs, runtime precheck logs, checkpoints, and optional audit outputs
- `runtime/`
  - execution-plane state and audit logs
- `scripts/`
  - the generated entrypoint and helper scripts used by the runtime

The most common mistake is to treat every log file as interchangeable. They are
not.

## The Main Log Surfaces

| Path | Produced by | Main question it answers |
| --- | --- | --- |
| `runtime/runtime.log` | execution plane | What did the worker or backend do to stage, launch, probe, collect, and terminate the run? |
| `artifacts/*.log` | task runtime | What did the task print or record for this workflow? |
| `artifacts/runtime-precheck.log` | training bundle entrypoint | Did the training runtime import the required packages and staged inputs before the main command ran? |
| `artifacts/training.log` | training runtime | What happened during training or rollout startup? |
| `artifacts/checkpoints/*/logging.jsonl` | training runtime | What metrics were emitted across training steps? |
| `artifacts/nvml-audit.jsonl` | NVML helper | What were GPU memory/utilization snapshots over time on a GPU training bundle? |
| `artifacts/nvml-audit.log` | NVML helper process | Did the NVML helper itself start, run, and stop correctly on a GPU training bundle? |

## What To Read In Order

For most failures, this is the shortest useful sequence:

1. `runtime/runtime.log`
2. one or more task logs under `artifacts/`
3. for training bundles, `artifacts/runtime-precheck.log`
4. for training bundles, `artifacts/checkpoints/*/logging.jsonl`
5. for GPU training bundles, `artifacts/nvml-audit.jsonl`

Why this order works:

- `runtime.log` tells you whether the execution plane itself was healthy
- task logs tell you what the main command did
- `runtime-precheck.log` tells you whether the staged training runtime was ready
- `logging.jsonl` tells you whether training was making real progress

## `runtime/runtime.log`

Use this when the problem feels operational rather than model- or task-specific.

Typical questions:

- Did the worker stage the bundle successfully?
- Did remote launch happen at all?
- Did status probing fail?
- Did collection return the expected files?

This file is especially important when:

- `orbit control run logs` looks incomplete
- remote staging fails
- a job never seems to start
- `worker collect` returns less than expected

## Training-Specific Log Surfaces

The files below are current training-path surfaces, not a guarantee for every
ORBIT bundle.

## `artifacts/runtime-precheck.log`

Use this when the bundle starts but fails before the real workload is underway.

This file is where the generated entrypoint records checks such as:

- whether the runtime can import `swift`
- whether `vllm` is available when required
- whether GPU bundles can import `pynvml`
- whether staged packages resolve from the expected path

For the current training path, this file is the first place to confirm that the
runtime is using the staged in-repo `ms-swift` fork rather than an unexpected
image-installed package.

## Task Logs Under `artifacts/`

The task/runtime logs tell you what the workload itself did after launch.

Typical files:

- `artifacts/stdout.log`
- `artifacts/stderr.log`
- task-specific logs such as `training.log`, rollout logs, or stage-specific
  training logs

Use them for:

- stack traces
- import/runtime exceptions after the precheck phase
- step progression
- rollout startup behavior
- task-specific warnings

For fast inspection:

```bash
tail -50 <bundle-dir>/artifacts/training.log
grep -E "OOM|OutOfMemory|Traceback|step" <bundle-dir>/artifacts/training.log | tail -40
```

## `logging.jsonl` Is a Training Metrics Log

`artifacts/checkpoints/*/logging.jsonl` is emitted by the training runtime. Use
it to inspect metrics progression, not execution-plane behavior.

Typical uses:

- confirm that training reached later steps
- inspect reward/loss movement
- verify that a resumed run is writing fresh metrics

Fast inspection example:

```bash
cat <bundle-dir>/artifacts/checkpoints/*/logging.jsonl | tail -20
```

Important terminology rule:

- this is a training metrics log
- it is not a Pydantic log

## Practical Triage Examples

### Case 1: The remote run never really starts

Read:

1. `runtime/runtime.log`
2. task-specific logs under `artifacts/`
3. if this is a training bundle, `artifacts/runtime-precheck.log`

Interpretation:

- if `runtime.log` never shows a clean launch path, debug the execution plane
- if launch happened but `runtime-precheck.log` fails on imports, debug the
  runtime image or staged inputs

### Case 2: The run starts and then crashes

Read:

1. `artifacts/training.log`
2. `artifacts/stderr.log`
3. `artifacts/checkpoints/*/logging.jsonl` if this is a training bundle

Interpretation:

- if logs show no real step progression, treat it as a startup/runtime issue
- if metrics progressed and then stopped, treat it as a mid-run training issue

### Case 3: Metrics look wrong even though the run finished

Read:

1. `artifacts/checkpoints/*/logging.jsonl`
2. `artifacts/training.log`

Interpretation:

- use `logging.jsonl` to identify when the metrics changed shape
- use `training.log` to understand what the runtime was doing at that time

## Related Guides

- [debugging.md](debugging.md)
- [nvml-gpu-audit.md](nvml-gpu-audit.md)
- [pydantic-validation.md](pydantic-validation.md)
- [test-runbook.md](test-runbook.md)
