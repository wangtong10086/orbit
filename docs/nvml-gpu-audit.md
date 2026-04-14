# NVML GPU Audit Guide

This guide explains the GPU memory audit files written by GPU training bundles.
Use it when debugging OOMs, unexpected GPU memory pressure, or low GPU
utilization.

This is a training-path helper surface. It is not a guaranteed artifact for
every `worker` run or every bundle type.

## What The NVML Audit Is

GPU training bundles may start a background helper that samples GPU state
through `pynvml`. In the current repository that helper is:

- `scripts/nvml_gpu_audit.py`

The generated training bundle starts it in the background and writes:

- `artifacts/nvml-audit.jsonl`
- `artifacts/nvml-audit.log`

The helper is part of the training-bundle runtime path, not a separate operator
tool you need to launch manually for normal runs.

## When It Is Present

Expect NVML audit files when all of these are true:

- the bundle is a GPU training bundle
- the generated entrypoint requested NVML auditing
- the runtime can import `pynvml`

The current entrypoint logic also records precheck behavior in
`artifacts/runtime-precheck.log`, including whether it had to install
`nvidia-ml-py`.

## The Two Output Files

### `artifacts/nvml-audit.jsonl`

This is the main artifact. It records structured JSONL events over time.

The important event types are:

- `start`
  - helper metadata such as hostname, PID, and polling interval
- `inventory`
  - initial GPU inventory and the first full device snapshot
- `sample`
  - repeated snapshots of GPU memory, utilization, and processes
- `stop`
  - helper shutdown marker
- `error`
  - helper-level failure such as import or NVML access failure

### `artifacts/nvml-audit.log`

This is the helper process stdout/stderr stream. Use it to confirm whether the
helper itself started and exited normally.

If `nvml-audit.jsonl` is missing or incomplete, check this file before assuming
the bundle never requested NVML auditing.

## What A Sample Contains

Each device snapshot can include:

- device index
- GPU UUID and name
- total, used, and free memory in MiB
- GPU and memory utilization percentages
- running processes with:
  - PID
  - process name
  - command line
  - per-process GPU memory usage when NVML exposes it

This matters because OOM debugging is often not just "the training process used
too much memory". Another PID may already own a large part of the device.

## How To Use It

### Step 1: Confirm the helper ran

Check:

- `artifacts/runtime-precheck.log`
- `artifacts/nvml-audit.log`

You want to confirm:

- `pynvml` import succeeded
- the helper was launched
- the helper did not immediately exit with an import/runtime error

### Step 2: Correlate with training failure timing

Check:

- `artifacts/training.log`
- `artifacts/nvml-audit.jsonl`

Look for:

- the last useful training line before failure
- the last NVML sample before failure

If the last samples already show very high `memory_used_mib` or another large
PID, the issue may be machine state or rollout colocate pressure rather than
just model configuration.

### Step 3: Inspect process-level ownership

Look inside `processes` for each device snapshot.

Use this to distinguish:

- the main training process consuming most memory
- rollout or teacher-side processes consuming memory
- unrelated leftover processes on the rental

### Step 4: Decide what kind of fix is appropriate

Use the evidence to separate these cases:

- training/config issue
  - model shape, batch size, sequence length, rollout settings
- colocated runtime issue
  - rollout server plus trainer competing for the same devices
- machine hygiene issue
  - unrelated or stale processes already using memory
- runtime environment issue
  - `pynvml` missing, helper not launching, or NVML unavailable

## Fast Inspection Patterns

Raw file inspection:

```bash
tail -20 <bundle-dir>/artifacts/nvml-audit.jsonl
tail -50 <bundle-dir>/artifacts/nvml-audit.log
grep -E "OOM|OutOfMemory|CUDA|Traceback" <bundle-dir>/artifacts/training.log | tail -40
```

Use the JSONL file together with:

- `artifacts/training.log`
- `artifacts/runtime-precheck.log`
- `runtime/runtime.log`

That combination tells you:

- whether the helper was requested
- whether it started
- what the GPU state looked like
- whether the training runtime failed before or after the spike

## Common Interpretations

### `error` event says `pynvml import failed`

Interpretation:

- the helper could not import the NVML Python binding
- read `runtime-precheck.log` to confirm whether the entrypoint attempted to
  install `nvidia-ml-py`

### `sample` events exist but no useful process data appears

Interpretation:

- NVML visibility may be limited on that runtime
- device-level memory totals are still useful, but per-process attribution may
  be incomplete

### `training.log` shows OOM and NVML shows memory nearly full beforehand

Interpretation:

- this is a real memory-pressure signal, not just a generic CUDA crash
- decide whether to change the training shape, rollout shape, or machine usage

## Related Guides

- [debugging.md](debugging.md)
- [logging-and-artifacts.md](logging-and-artifacts.md)
- [test-runbook.md](test-runbook.md)
