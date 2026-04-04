# Operations Guide

This document covers runtime prerequisites, environment configuration, and
machine-level operational constraints. It does not describe refactor history.

## Configuration Loading

Primary configuration entrypoint:

- `forge/config.py`

`.env` backfill order:

1. repository root `.env`
2. parent-directory `.env`

Only keys that are not already present in the process environment are backfilled
from dotenv files.

## Important Environment Variables

Common variables read by `ForgeConfig` include:

- `API_URL`
- `HF_TOKEN`
- `HF_DATASET_REPO`
- `HF_GAME_TEACHER_REPO`
- `HF_GAME_POLICY_REPO`
- `HF_RUNTIME_REPO`
- `HF_BACKUP_REPO`
- `AFFINE_DEFAULT_EXEC_IMAGE`
- `TARGON_API_KEY`
- `TARGON_PROJECT_ID`
- `TARGON_SSH_KEY_UID`
- `CHUTES_API_KEY`
- `WANDB_API_KEY`

For the official training example, the minimum launch secrets are:

- `HF_TOKEN`
- `TARGON_API_KEY`
- `TARGON_PROJECT_ID`
- `TARGON_SSH_KEY_UID`

For automatic model upload after training:

- `HF_TOKEN` must be able to create the target model repo when
  `publish.create_repo=true`
- `HF_TOKEN` must be able to upload model files to the target repo
- the same launch flow supports both private and public repos through
  `publish.private`

Common path settings:

- `project_root`: repository root
- `data_dir`: `data/`
- `machines_file`: `machines.json`
- `backup_dir`: `~/backups/checkpoints`

## Local Execution

### Local Docker

```bash
python -m forge worker run <bundle-dir> --placement local --launch-mode docker_image --foreground
```

Behavior:

- mounts the project into the container
- mounts the bundle into the container
- runs `scripts/entrypoint.sh`
- writes logs and results back into bundle artifacts/runtime

### Local Host Process

```bash
python -m forge worker run <bundle-dir> --placement local --launch-mode host_process --foreground
```

Behavior:

- executes the bundle entrypoint directly on the host
- writes logs into `artifacts/`
- writes state and result files into `runtime/`
- appends execution-plane runtime actions into `runtime/runtime.log`

## Targon Rental Execution

Current public Targon path:

- `forge control submit ... --template targon-rental-docker`
- `forge control submit ... --template targon-rental-host`
- `forge worker run ... --placement targon_rental --launch-mode docker_image`
- `forge worker run ... --placement targon_rental --launch-mode host_process`

Current Targon constraints:

- rental only
- no serverless support in the main execution abstraction
- no app-path abstraction in the main execution abstraction

Current execution behavior:

- target resolution comes from `machines.json`
- the backend stages project and bundle archives to the remote machine
- `targon-rental-host` executes bundles directly on the rental host process
- `targon-rental-docker` still exists for Docker-based rentals, but should not be the default path for GPU workloads on Targon
- if `HF_RUNTIME_REPO` and `HF_TOKEN` are available, runtime staging may use HF
  instead of direct SSH upload
- runtime backends append staging, launch, status, collect, and terminate events
  to `bundle/runtime/runtime.log`

Operational preference for Targon rentals:

- provision the rental from the execution image you actually want to run
- enable SSH inside that image
- use `targon-rental-host` for bundle execution
- prefer `forge control launch train --config ...` when following the official
  production-style training example

Do not assume GPU-capable Docker-in-Docker is available or reliable on Targon
rentals.

## Machines and Targets

Targon rental placement currently resolves remote machines through `machines.json`.

Operational rules:

- if a command requires a target, pass it explicitly
- do not treat a checked-in `machines.json` as a default production inventory
- use an isolated rental machine for runtime validation
- clean up temporary validation machines after the run

## Adjacent External Dependencies

Some workflows are not fully self-contained within this repository.

Known external neighbors:

- `../affinetes`
- `../liveweb-arena`

Implication:

- a command may be valid as a workflow even if it still requires an adjacent
  checkout or a task-specific image

## Image-Dependent Task Notes

Execution-path validity and task-image validity are separate concerns.

Examples:

- a Targon rental path may be healthy while a task still fails because the image
  is missing `pyspiel`
- a data-generation image may need additional Python packages or model/runtime
  credentials that are not present in the default execution image

When a task requires non-default dependencies, choose or build an image that
matches the task.

## Runtime Audit Files

Execution-plane runs now produce two complementary log surfaces inside the
bundle:

- `artifacts/*.log`
  - task stdout/stderr and task-specific logs such as `training.log`
- `runtime/runtime.log`
  - execution-plane actions such as remote staging, launch submission, status
    probes, artifact collection, and termination

After `forge worker collect` or `forge control run collect`, `runtime.log` is
included in the artifact manifest under `logs.runtime.log`.
