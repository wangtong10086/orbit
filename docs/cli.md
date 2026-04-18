# CLI Guide

This document covers the current command surface. It explains which command
family owns which workflow. It does not restate the full architecture model.

## Root CLI

```bash
python3 -m orbit --help
```

Current command families:

- `control`
- `worker`
- `data`
- `remote`
- `monitor`

Optional extras currently affect dependency availability more than top-level
command visibility.

## Recommended Usage Order

For most users, the command families line up like this:

1. use `control` locally to create experiments and submit remote jobs
2. use `run status|logs|collect` to inspect the Targon execution lifecycle
3. use `worker` directly only when you want to debug a bundle or runtime path
4. use `remote` and `monitor` for operational workflows rather than first-run
   task submission

## `control`

```bash
python3 -m orbit control --help
```

Use `control` when you need orchestration, experiment records, or execution
template selection.

Primary documented path:

- local `control`
- template-driven submit
- remote execution on `targon_rental + host_process`

Current command groups:

- `template`
  - `list`
  - `show`
  - `validate`
- `experiment`
  - `create`
  - `list`
  - `show`
  - `set-status`
- `prepare`
  - `train`
  - `eval`
  - `collect`
- `launch`
  - `train`
- `submit`
  - `train`
  - `eval`
  - `collect`
- `run`
  - `status`
  - `logs`
  - `collect`
  - `terminate`

Key rule:

- `submit` selects execution through `--template <id>`
- `targon-rental-host` is the default documented template for first remote runs
- `launch train --config <path>` is the supported one-command training entrypoint
  when you want provisioning + experiment creation + submit from a single YAML
- `run status|logs|collect|terminate --run-key <stage>` lets you inspect a
  specific staged task record when one experiment owns multiple runs of the
  same job kind

## `worker`

```bash
python3 -m orbit worker --help
```

Use `worker` when you already have a bundle and want to execute it directly.

Current commands:

- `validate-bundle`
- `run`
- `status`
- `logs`
- `collect`
- `terminate`

Execution-plane logging behavior:

- runtime actions are appended to `bundle/runtime/runtime.log`
- `worker collect` returns `runtime.log` as part of `manifest.logs`
- task output logs such as `stdout.log`, `stderr.log`, and `training.log`
  remain under `artifacts/`
- use [debugging.md](debugging.md) for the debugging flow and
  [logging-and-artifacts.md](logging-and-artifacts.md) for the full log-surface
  map

Current execution dimensions:

- placement
  - `local`
  - `targon_rental`
- launch mode
  - `host_process`
  - `docker_image`

Current public support matrix:

- `local + host_process`
- `local + docker_image`
- `targon_rental + docker_image`
- `targon_rental + host_process`

Documentation maturity:

| Path | Status | Notes |
| --- | --- | --- |
| local `control` -> `targon_rental + host_process` | Recommended + validated | Default quick-start path |
| local `control` -> `targon_rental + docker_image` | Documented but secondary | Specialized path for Docker-oriented rentals |
| local `worker` -> `local + host_process` | Documented but secondary | Local debugging |
| local `worker` -> `local + docker_image` | Documented but secondary | Local Docker debugging |

Operational preference on Targon rentals:

- prefer `host_process` for GPU tasks on direct-image rentals
- treat `docker_image` on Targon as a specialized path, not the default remote
  training path
- after `worker collect`, inspect `runtime/runtime.log` when you need execution
  audit details rather than task stdout/stderr alone
- inspect [nvml-gpu-audit.md](nvml-gpu-audit.md) when GPU training bundles write
  NVML audit files

## `data`

```bash
python3 -m orbit data --help
```

Use `data` for dataset creation, ingestion, sync, and publishing workflows.

Current limitation:

- some `data` subcommands still expose convenience orchestration in the `data`
  command family instead of moving every remote workflow into `control`

Current categories:

- dataset utilities
  - `merge`
  - `analyze`
  - `validate`
  - `filter`
- canonical / HF sync
  - `status`
  - `upload`
  - `ingest`
  - `canonical-upload`
  - `hf-sync`
  - `canonical-sync`
  - `publish-mixed`
- data generation
  - `liveweb-gen`
  - `memorygym-gen`
  - `memorygym-split`
  - `navworld-gen`
  - `aggregate`
- GAME-specific tooling
  - `game-build-policy`
  - `game-gen`
  - `game-policy-model-status`
  - `game-policy-status`
  - `game-train-policy-model`
  - `game-upload-teacher`
  - `game-build-expert-dataset`
  - `game-selfplay-train`
  - `game-selfplay-status`
  - `game-selfplay-eval`
  - `game-selfplay-resume`
- SWE-specific tooling
  - `swe-collect`

## `remote`

```bash
python3 -m orbit remote --help
```

`remote` is an operational sidecar, not the main task execution surface.

Current command groups:

- `machine`
- `targon`
- `deploy`

Use it for machine inventory, direct Targon debugging, and deployment-adjacent
operations.

## `monitor`

```bash
python3 -m orbit monitor --help
```

Current commands:

- `leaderboard`
- `weaknesses`

## Recommended Usage

- Use `control` for the primary documented Targon workflow.
- Use `worker` for bundle-first execution workflows and local debugging.
- Use `data` for generation, ingestion, and publishing tasks.
- Use `remote` only for operational debugging or machine-level actions.
- Use `monitor` for monitoring and leaderboard inspection.

## SWE Collection

Primary SWE collection entrypoint:

```bash
python3 -m orbit data swe-collect --help
```

Use `swe-collect` when you need to run the upstream `affinetes`
`SWE-INFINITE` environment through ORBIT's thin black-box wrapper.

Current commands:

- `python3 -m orbit data swe-collect evaluate`
- `python3 -m orbit data swe-collect synthesize`
- `python3 -m orbit data swe-collect openenv reset`
- `python3 -m orbit data swe-collect openenv state`
- `python3 -m orbit data swe-collect openenv checkpoint`
- `python3 -m orbit data swe-collect openenv restore`
- `python3 -m orbit data swe-collect openenv step`
- `python3 -m orbit data swe-collect openenv stop`

Current rule:

- `evaluate` resolves an external `affinetes` checkout by exact commit and
  runs upstream `InfiniteActor.evaluate()` without rewriting agent or verify
  semantics
- `synthesize` runs a thin ORBIT controller above upstream OpenEnv and records
  raw `reset/checkpoint/restore/step/stop` events plus a small run manifest
- `synthesize` supports:
  - one OpenAI-compatible student endpoint via `--model --api-base`
  - an optional teacher endpoint via `--teacher-model --teacher-api-base`
  - checkpoint-aware retry knobs `--max-root-retries` and
    `--max-edit-retries`
  - `responses.create(...)` as the first model-call path, with automatic
    fallback to `chat.completions.create(...)` when the student endpoint does
    not implement `/v1/responses`
- `openenv` starts a thin stateful bridge around upstream
  `InfiniteActor.reset()/state()/checkpoint()/restore()/step()/stop()`
- ORBIT records raw upstream outputs plus thin manifests under the selected
  output directory
- the historical local staged collector under `orbit/data/swe_collection/` is
  not the active documented interface
