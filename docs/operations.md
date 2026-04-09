# Operations Guide

This document covers runtime prerequisites, environment configuration, and
machine-level operational constraints. It does not describe refactor history.

## Default Deployment Pattern

The primary documented and validated deployment pattern for this repository is:

- local control plane
- Targon rental execution
- launch mode `host_process`
- template `targon-rental-host`

Other execution combinations remain available, but this guide is centered on
the Targon-first path because that is the main intended use case.

## Configuration Loading

Primary configuration entrypoint:

- `orbit/config.py`

`.env` backfill order:

1. repository root `.env`
2. parent-directory `.env`

Only keys that are not already present in the process environment are backfilled
from dotenv files.

Launch-time implication:

- `orbit control launch train --config ...` now performs required-env validation
  after dotenv backfill
- shell-exported values still win over `.env`
- official training launches therefore work with either shell exports or a
  populated repository `.env`

## Important Environment Variables

Common variables read by `OrbitConfig` include:

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
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`

### Required for local control + Targon execution

- `TARGON_API_KEY`
- `TARGON_PROJECT_ID`
- `TARGON_SSH_KEY_UID`

### Required for training artifact/model publishing

- `HF_TOKEN`

### Required for observability

- `WANDB_API_KEY` for the official training launch when `report_to: wandb`

### Optional for OpenAI-compatible API workflows

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`

### Optional / project-specific

- `API_URL`
- `HF_DATASET_REPO`
- `HF_GAME_TEACHER_REPO`
- `HF_GAME_POLICY_REPO`
- `HF_RUNTIME_REPO`
- `HF_BACKUP_REPO`
- `AFFINE_DEFAULT_EXEC_IMAGE`
- `CHUTES_API_KEY`

For the official training example, the minimum launch secrets are:

- `HF_TOKEN`
- `TARGON_API_KEY`
- `TARGON_PROJECT_ID`
- `TARGON_SSH_KEY_UID`
- `WANDB_API_KEY`
Default training-launch behavior:

- control-side training launch now defaults to `report_to: wandb`
- if the launch config does not set `training.wandb_run_name`, the launcher uses
  `experiment.id`
- if a run should not report to Weights & Biases, set `training.report_to: none`
  in the launch config to suppress the `WANDB_API_KEY` requirement

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

Recommended `.env` block for the official training flow:

```dotenv
TARGON_API_KEY=...
TARGON_PROJECT_ID=...
TARGON_SSH_KEY_UID=...
HF_TOKEN=...
WANDB_API_KEY=...
```

## Execution Matrix and Maturity

Current public execution paths:

- `local + host_process`
- `local + docker_image`
- `targon_rental + host_process`
- `targon_rental + docker_image`

Documentation maturity:

| Path | Status | Notes |
| --- | --- | --- |
| local `control` -> `targon_rental + host_process` | Recommended + validated | Primary documented workflow |
| local `control` -> `targon_rental + docker_image` | Documented but secondary | Docker-oriented rentals |
| local `worker` -> `local + host_process` | Documented but secondary | Local debugging |
| local `worker` -> `local + docker_image` | Documented but secondary | Local Docker debugging |

## Targon Rental Execution

Targon is the primary documented remote platform for ORBIT rather than a
side provider.

Current public Targon path:

- `orbit control submit ... --template targon-rental-docker`
- `orbit control submit ... --template targon-rental-host`
- `orbit worker run ... --placement targon_rental --launch-mode docker_image`
- `orbit worker run ... --placement targon_rental --launch-mode host_process`

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
- for large local training datasets on `targon-rental-*` launches, the control
  plane now stages the dataset into `HF_RUNTIME_REPO`/`HF_BACKUP_REPO` and the
  rental downloads it directly from Hugging Face before training starts
- runtime backends append staging, launch, status, collect, and terminate events
  to `bundle/runtime/runtime.log`

Operational preference for Targon rentals:

- provision the rental from the execution image you actually want to run
- enable SSH inside that image
- use `targon-rental-host` for bundle execution
- prefer local `control` plus remote execution as the normal operating model
- prefer `orbit control launch train --config ...` when following the official
  production-style training example

Do not assume GPU-capable Docker-in-Docker is available or reliable on Targon
rentals.

## Local Execution

### Local Docker

```bash
python3 -m orbit worker run <bundle-dir> --placement local --launch-mode docker_image --foreground
```

Behavior:

- mounts the project into the container
- mounts the bundle into the container
- runs `scripts/entrypoint.sh`
- writes logs and results back into bundle artifacts/runtime

### Local Host Process

```bash
python3 -m orbit worker run <bundle-dir> --placement local --launch-mode host_process --foreground
```

Behavior:

- executes the bundle entrypoint directly on the host
- writes logs into `artifacts/`
- writes state and result files into `runtime/`
- appends execution-plane runtime actions into `runtime/runtime.log`

## Machines and Targets

Targon rental placement currently resolves remote machines through `machines.json`.

Operational rules:

- if a command requires a target, pass it explicitly
- for user-facing docs, treat local `control` plus explicit `--target` as the
  standard submission pattern
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

## Native GKD Runtime Expectations

The default execution image is now expected to support native `ms-swift` GKD
directly.

Current baseline:

- `torch`, `transformers`, `ms-swift`, and `vllm` are preinstalled in the
  default execution image
- `orbit/setup/bootstrap.sh` installs the same validated runtime stack on a
  fresh rental
- the stable default recipe is `attn_impl: sdpa` with `packing: false`
- `flash-attn` is optional and should only be installed for recipes that
  explicitly require it

If a training config uses `training.train_type: rlhf` and
`training.rlhf_type: gkd`, the runtime must be able to import:

- `torch`
- `transformers`
- `swift`
- `vllm`

The bundle entrypoint now checks these packages before invoking `swift rlhf` so
runtime drift fails early with a clear error.

### External Teacher Servers

ORBIT does not manage teacher-server lifecycle. For external native GKD
teachers, pass the upstream `ms-swift` fields through
`training.swift_passthrough`.

For vLLM teacher servers:

- `gkd_logits_topk` must be less than or equal to the server's
  `--max-logprobs`
- `gkd_logits_topk: 64` therefore requires `--max-logprobs 64` or higher
- a reusable launch template lives at
  [`../scripts/vllm_teacher_qwen3_235b_tp8.sh`](../scripts/vllm_teacher_qwen3_235b_tp8.sh)

## Runtime Audit Files

Execution-plane runs now produce two complementary log surfaces inside the
bundle:

- `artifacts/*.log`
  - task stdout/stderr and task-specific logs such as `training.log`
- `runtime/runtime.log`
  - execution-plane actions such as remote staging, launch submission, status
    probes, artifact collection, and termination

After `orbit worker collect` or `orbit control run collect`, `runtime.log` is
included in the artifact manifest under `logs.runtime.log`.
