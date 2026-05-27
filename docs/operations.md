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

Training launch persistence rule:

- experiment YAML now stores `train_config` as the effective training config
  that ORBIT actually passes into the runtime path
- the original launch-file declaration is stored under
  `results.extra.training_launch_config_declared`
- the launcher-resolved config, including derived fields such as
  auto-filled `wandb_run_name`, is stored under
  `results.extra.training_launch_config_resolved`
- for bucketed training, per-stage effective configs are stored under
  `results.extra.training_bucket_plan_resolved`
- for patched native GKD with `teacher_data_mode: offline_topk`, the effective
  config also records the resolved offline top-k field names

Patched `ms-swift` runtime note:

- ORBIT now maintains a local fork of `ms-swift` under
  `packages/affine_ms_swift/vendor/ms_swift_fork`
- the maintenance entrypoint for refreshing that fork is
  `scripts/sync_ms_swift_fork.py`
- the tracked patch set still lives in `scripts/apply_ms_swift_patches.py`, but
  it is now applied to the local fork source tree rather than treated as a
  site-packages runtime patch as the primary path
- the patch set adds offline-topk GKD support and
  `swift sample --sampler_type gkd_topk`
- training bundles now stage the local fork and prepend it to `PYTHONPATH` so
  remote `swift` processes resolve the in-repo fork before the image-installed
  package
- April 10, 2026 real validation confirmed remote `swift` imports resolve from
  the staged fork path during a Targon MemoryGym smoke:
  `/root/orbit-execution/.../bundle/inputs/runtime-swift-fork-ms_swift_fork/swift/__init__.py`
- the design, runtime flow, and dataset contract for this path are documented
  in [`offline-gkd.md`](offline-gkd.md)
- the complete operator tutorial, including collection and Hugging Face upload,
  is documented in [`offline-gkd-quickstart.md`](offline-gkd-quickstart.md)

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

### OpenEnv SWE image staging

For large SWE synth or eval batches, the documented path is now:

1. resolve a concrete `selected_tasks.json`
2. prewarm all required task images onto the collector
3. pass the student ready gate
4. only then launch the batch through the tracked bounded launcher

Use:

```bash
python3 -m orbit data swe-collect prewarm-images \
  --selected-tasks-json /abs/path/to/selected_tasks.json \
  --cache-dir /tmp/swe-infinite-cache \
  --output /abs/path/to/image_prewarm.json
```

Current default prewarm policy:

- `--image-pull-timeout-secs 1800`
- `--image-pull-concurrency 4`
- `--image-pull-retries 3`

The prewarm report is a hard gate for benchmark-quality runs:

- if any image fails prewarm, do not start the batch
- if all images are `cached` or `pulled`, launch can proceed without first-wave
  registry dependence during `reset()`

Stateful OpenEnv server behavior for the active ORBIT bridge:

- startup stale-container cleanup is disabled by default to avoid concurrent
  servers deleting each other’s `swe-infinite-openenv-*` containers
- if a task image is already present locally, ORBIT skips upstream
  unconditional `docker pull` and goes straight to `docker run`
- if the image is missing, ORBIT uses the configurable pull timeout and retry
  policy instead of the upstream fixed `300s` pull timeout

The active OpenEnv bridge now injects these defaults into its server
environment:

- `ORBIT_OPENENV_ALLOW_STARTUP_STALE_CLEANUP=false`
- `ORBIT_OPENENV_DOCKER_PULL_TIMEOUT_SECS=1800`
- `ORBIT_OPENENV_DOCKER_PULL_RETRIES=3`
- `ORBIT_OPENENV_DOCKER_PULL_RETRY_DELAY_SECS=5`

### OpenEnv SWE runtime bootstrap

Large SWE batches no longer rely on rebuilding a fresh per-task virtualenv
under each task output directory.

The active path now uses a shared immutable runtime cache on the collector:

- cache root:
  - `~/.cache/orbit/affinetes_swe_runtime/`
- cache key includes:
  - exact upstream ref
  - upstream Python executable and Python version
  - `environments/SWE-INFINITE/requirements.txt` content hash

Task-local `.runtime/` directories still exist, but they are now limited to
task-specific sockets, logs, and home paths. The Python executable used by the
upstream bridge resolves to the shared cache venv instead of rebuilding a full
venv for every task.

Bootstrap hardening rules:

- if `python -m pip` is unavailable in the shared runtime venv, ORBIT runs:
  - `python -m ensurepip --upgrade`
- the requirements stamp now binds:
  - upstream ref
  - Python version
  - requirements hash

This reduces startup cost and prevents transient `.runtime/venv` contention
from surfacing as `No module named pip`.

### OpenEnv SWE bounded batch launch

For large clean-eval SWE runs, do not use ad hoc `nohup 100` fan-out anymore.

Use the tracked bounded launcher:

```bash
python3 scripts/swe_launch_batch.py \
  --selected-tasks-json /abs/path/to/selected_tasks.json \
  --image-prewarm-json /abs/path/to/image_prewarm.json \
  --output-dir /abs/path/to/campaign/run \
  --upstream-repo-path /abs/path/to/affinetes \
  --upstream-ref <exact-affinetes-commit> \
  --cache-dir /tmp/swe-infinite-cache \
  --model <student-model> \
  --api-base http://127.0.0.1:30001/v1 \
  --api-key dummy \
  --student-log-path /root/logs/sglang.log \
  --student-ssh-host <student-host> \
  --student-ssh-port <student-ssh-port>
```

Current default launcher policy:

- `bootstrap_concurrency = 8`
- `max_live_rollouts = 32`
- `model_timeout = 300`
- `transport_only_retries = 1`
- `max_infra_restarts = 1`
- `max_transport_restarts = 1`

The launcher is the documented large-batch path because it provides:

- hard validation of `selected_tasks.json`
- hard validation of `image_prewarm.json`
- a student ready gate before any task starts
- explicit campaign state in `campaign_state.json`
- periodic rollout metrics in `campaign_metrics.jsonl`
- cleanup of orphan `openenv_server` processes

The student ready gate requires all of:

- `/v1/models` returning the expected model id
- `/model_info` responding successfully
- one smoke `chat.completions` request succeeding
- the student log containing the server-ready marker

For local Qwen student endpoints, the smoke gate accepts either:

- normal `message.content`
- or `message.reasoning_content`

because some local Qwen responses return the probe only in
`reasoning_content`.

### Optional / project-specific

- `API_URL`
- `HF_DATASET_REPO`
- `HF_GAME_TEACHER_REPO`
- `HF_GAME_POLICY_REPO`
- `HF_RUNTIME_REPO`
- `HF_BACKUP_REPO`
- `AFFINE_DEFAULT_EXEC_IMAGE`
- `CHUTES_API_KEY`

Teacher-secret rule for offline-topk GKD:

- offline-topk training itself does not need teacher credentials
- only the offline collection phase needs teacher access, for example a local
  `teacher_model` or an external `teacher_model_server`
- sampled offline-topk datasets should be uploaded to a Hugging Face dataset
  repo immediately after collection to avoid losing the only copy on a local
  disk or rental filesystem
- the helper wrapper `scripts/sample_offline_topk_and_upload.py` uses the same
  dotenv backfill order as the training launcher:
  repository `.env`, then parent `.env`, without overriding already-exported
  shell values
- for canonical-scale collection, prefer
  `scripts/collect_offline_topk_dataset.py` over many parallel `swift sample`
  processes; it prepares once, collects per bucket, and uploads incremental
  parts to Hugging Face
- for canonical-scale bucketed training, the runtime bucket splitter now uses
  batch chat-template rendering plus batch fast-tokenizer calls, and writes
  `runtime/bucketed/progress.json` continuously while bucket files are being
  appended; `bucket_manifest.json` remains the final completion artifact

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

## Automated Public Release

The private development repository is now responsible for publishing the public
snapshot to `wangtong10086/ORBIT`.

Required private-repo GitHub Actions secret:

- `PERSONAL_PROJECT_ORBIT_TOKEN`

That token must be able to:

- push to `wangtong10086/ORBIT`
- dispatch workflows in `wangtong10086/ORBIT`
- read workflow run status from `wangtong10086/ORBIT`

The private-repo workflow `publish-public.yml` now:

- exports the public snapshot from `release/public-export.yaml`
- includes the exported internal package trees under `packages/` because the
  public Docker image and public validation path depend on them
- validates the exported snapshot before publish
- force-pushes the validated snapshot to `wangtong10086/ORBIT:main`
- dispatches public `CI`, `Docs`, and `Docker`
- waits for those public workflows to complete successfully

The private `Docker` and `publish-public` workflows now auto-trigger on
`packages/**` changes in addition to `Dockerfile`, `orbit/**`, and related
workflow files, because the shipped image and public snapshot both consume the
package split directly.

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
- the repository Dockerfile now clones `AffineFoundation/MemoryGym` during the
  image build instead of assuming a tracked local `repos/MemoryGym/` checkout
  is present in CI

### Local Host Process

```bash
python3 -m orbit worker run <bundle-dir> --placement local --launch-mode host_process --foreground
```

Behavior:

- executes the bundle entrypoint directly on the host
- writes logs into `artifacts/`
- GPU training bundles may also write `artifacts/nvml-audit.jsonl` and
  `artifacts/nvml-audit.log` from a background NVML audit process
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
- that helper script is included in the public release snapshot

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

Read these guides for usage rather than only file definitions:

- [debugging.md](debugging.md) for the overall debugging flow
- [logging-and-artifacts.md](logging-and-artifacts.md) for the full artifact map
- [nvml-gpu-audit.md](nvml-gpu-audit.md) for GPU memory analysis
- [pydantic-validation.md](pydantic-validation.md) for contract/schema failures
