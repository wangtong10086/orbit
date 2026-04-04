# CLI Guide

This document covers the current command surface. It explains which command
family owns which workflow. It does not restate the full architecture model.

## Root CLI

```bash
python -m forge --help
```

Current command families:

- `control`
- `worker`
- `data`
- `remote`
- `monitor`

Optional extras currently affect dependency availability more than top-level
command visibility.

## `control`

```bash
python -m forge control --help
```

Use `control` when you need orchestration, experiment records, or execution
template selection.

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
- `launch train --config <path>` is the supported one-command training entrypoint
  when you want provisioning + experiment creation + submit from a single YAML

## `worker`

```bash
python -m forge worker --help
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

Operational preference on Targon rentals:

- prefer `host_process` for GPU tasks on direct-image rentals
- treat `docker_image` on Targon as a specialized path, not the default remote
  training path
- after `worker collect`, inspect `runtime/runtime.log` when you need execution
  audit details rather than task stdout/stderr alone

## `data`

```bash
python -m forge data --help
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
  - `swe-status`
  - `swe-sync`

## `remote`

```bash
python -m forge remote --help
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
python -m forge monitor --help
```

Current commands:

- `leaderboard`
- `weaknesses`

## Recommended Usage

- Use `control` for experiment-driven workflows.
- Use `worker` for bundle-first execution workflows.
- Use `data` for generation, ingestion, and publishing tasks.
- Use `remote` only for operational debugging or machine-level actions.
- Use `monitor` for monitoring and leaderboard inspection.
