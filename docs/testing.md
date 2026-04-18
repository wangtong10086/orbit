# Testing Guide

This document describes the current testing reality. It covers what is actually
validated today, not an idealized future state.

## Test Layers

The repository currently relies on three practical layers:

- unit and integration tests under `tests/`
- CLI smoke checks
- real runtime validation records under `logs/real-tests/`

## What Is The Primary Validated Deployment Pattern?

The most important validated deployment pattern for this repository is:

- local control plane
- remote execution on Targon rentals
- preferred launch mode `host_process`
- primary documented template `targon-rental-host`

This matters because the user-facing docs prioritize validated Targon-backed
workflows over local-only debugging paths.

## Common CLI Checks

These help commands are expected to work:

```bash
python3 -m orbit --help
python3 -m orbit control --help
python3 -m orbit worker --help
python3 -m orbit data --help
python3 -m orbit remote --help
python3 -m orbit monitor --help
```

## Pytest Baseline

Current broad regression command:

```bash
pytest -q tests -q
```

Current status:

- passing

Additional targeted suites used during recent refactor closeout:

```bash
pytest -q tests/test_compute.py tests/test_control.py tests/test_data_cli.py tests/test_execution.py -q
```

Current status:

- passing

Additional targeted suites for native ms-swift training launch configs:

```bash
pytest -q tests/test_execution.py tests/test_training.py tests/test_training_launch.py -q
```

Current status:

- passing

Additional targeted suites for the RL package-boundary refactor:

```bash
pytest -q tests/test_rl_ecosystem.py tests/test_memorygym_plugin.py tests/test_core_boundaries.py -q
```

Current status:

- passing

Additional targeted suites for the local `ms-swift` fork path:

```bash
pytest -q tests/test_rl_ecosystem.py tests/test_training.py tests/test_training_launch.py tests/test_memorygym_plugin.py -q
```

Current status:

- passing

Additional targeted suite for the 2026-04-06 Targon ablation runtime fix:

```bash
pytest -q tests/test_execution.py -q
```

Current status:

- passing

## What the Current Suite Proves

Today’s suite covers:

- current CLI command registration
- template-driven control paths
- generic execution contracts and worker flows
- data CLI and adjacent generation helpers
- compute and SSH/Targon transfer edge cases
- training-launch config validation for native `ms-swift` SFT and RLHF runs,
  including GKD-specific passthrough fields
- frozen task-source evaluation bundle wiring
- the SWE black-box integration, including:
  - exact-ref external `affinetes` checkout validation
  - local-path and clone-based upstream repo resolution
  - black-box `evaluate()` invocation and raw output indexing
  - stateful OpenEnv `reset/state/checkpoint/restore/step/stop` bridging
  - CLI wiring for `orbit data swe-collect evaluate` and `openenv ...`
  - collection adapter wiring for black-box `evaluate` mode

## External Dependency Notes

Some workflows still rely on adjacent repositories or richer runtime images.

Examples:

- evaluation workflows may require `affinetes`
- LIVEWEB workflows may require `liveweb-arena`
- task-specific remote runs may require images with extra packages such as
  `pyspiel`

The core test suite is structured to remain runnable even when some of these
adjacent repositories are not installed locally.

## Real Validation

Code-level green tests are not the whole story for runtime-facing changes.

For runtime, provider, or remote-execution changes, also consult:

- [test-runbook.md](test-runbook.md)

Current SWE collection note:

- the active path is the external `affinetes` black-box integration
- historical staged-search experiments remain under `logs/real-tests/`, but
  they are not the active documented implementation
- code-level tests now cover:
  - exact-ref upstream repo validation
  - clone-vs-path runtime resolution
  - black-box evaluate manifest/raw output writing
  - OpenEnv bridge reset/state/checkpoint/restore/step/stop roundtrip
  - collection adapter wiring
- local real validation for the black-box path is recorded at
  `logs/real-tests/swe-blackbox-local-20260418/`
- that local record ran:
  - wrapper `codex/geopy`
  - direct upstream `codex/geopy`
  - wrapper `miniswe/rubocop`
  - direct upstream `miniswe/rubocop`
- the local record captured:
  - wrapper and direct upstream `codex` both failing with
    `docker_error: Failed to install Codex CLI in container`
  - wrapper and direct upstream `miniswe` both timing out under the same
    90-second outer window
- remote Targon validation is recorded at
  `logs/real-tests/swe-blackbox-targon-20260418/`
- that remote record used:
  - Targon project `prj-0f96o65vhukw`
  - Targon SSH key `shk-sdnwzg2ghpye`
  - isolated rental workload `wrk-ucjqnk3icdei`
  - image `ghcr.io/manifold-inc/ubuntu-systemd-docker:v1`
  - resource `cpu-small`
- that remote record captured:
  - wrapper `codex/geopy` failing with the same upstream
    `docker_error: Failed to install Codex CLI in container`
  - wrapper `miniswe/rubocop` reaching the same upstream startup path and
    timing out after a valid `CHUTES_API_KEY` run
  - cleanup completed and the final rental list was empty
- local real validation for upstream OpenEnv checkpoint/restore is recorded at
  `logs/real-tests/swe-openenv-checkpoint-20260418/`
- that local record ran:
  - direct upstream `reset -> checkpoint -> step -> state -> checkpoint -> step -> restore -> step -> restore -> step -> stop`
  - ORBIT wrapper `openenv reset/checkpoint/state/restore/step/stop` against the same exact upstream ref
- that local record captured:
  - restore to the edited checkpoint producing `FILE_PRESENT`
  - restore to the baseline checkpoint producing `FILE_MISSING`
- remote Targon validation for upstream OpenEnv checkpoint/restore is recorded
  at `logs/real-tests/swe-openenv-checkpoint-targon-20260418/`
- that remote record used:
  - isolated `cpu-small` rental `wrk-pnhjciw3rfj3`
  - image `ghcr.io/manifold-inc/ubuntu-systemd-docker:v1`
  - upstream fork ref `7e1f48ec380a2e254d72c9cf6cc1e9cda0f8cc7e`
- that remote record captured:
  - the first roundtrip failure due to `dockerd` not running inside the rental
  - a rerun of the original `openenv reset` command after manual `dockerd`
    startup
  - a downstream rerun of the full `reset -> checkpoint -> step -> restore -> stop`
    script
  - `probe1=FILE_PRESENT`
  - `probe0=FILE_MISSING`
Current native training validation status:

- a clean repository snapshot was installed into a fresh local venv
- `.env` backfill was used for Targon, Hugging Face, and W&B credentials
- `python3 -m orbit control launch train` was real-validated from that snapshot
- native `ms-swift` SFT and GKD configs were both validated as supported launch
  shapes
- real Targon validation confirmed remote checkpoint creation through the normal
  training launch path

Additional runtime evidence from April 8, 2026:

- the original native GKD failure on rental `gkdsmk-92837z` was
  `ModuleNotFoundError: vllm`
- rerunning that original remote `swift rlhf --rlhf_type gkd` command after
  installing `vllm` succeeded and wrote `checkpoint-10`
- a downstream fresh `orbit control launch train` native GKD smoke also
  succeeded with `Qwen/Qwen3-0.6B -> Qwen/Qwen3-8B` on `tmp/game.jsonl`
- the teacher-server compatibility check showed that `top_logprobs=64`
  requires a vLLM server launched with `--max-logprobs 64` or higher

Additional runtime evidence from April 9, 2026:

- bucketed SFT is now real-validated through the normal
  `python3 -m orbit control launch train` path
- a fresh bucketed full-SFT smoke completed on an isolated Targon rental and
  uploaded the final model artifact to Hugging Face
- a fresh bucketed LoRA-SFT smoke also completed on an isolated Targon rental
  and uploaded the final adapter artifact to Hugging Face
- the bucketed training implementation now uses bundle-staged helper scripts
  under `scripts/` and `inputs/` so remote clean-bundle staging does not drop
  them
- April 12, 2026 hotfix validation on an 8xH200 rental confirmed that the
  bucket splitter now uses batch chat-template rendering plus batch fast
  tokenization, and exposes live progress under `runtime/bucketed/progress.json`
- that same hotfix raised observed CPU utilization from a mostly-idle machine
  profile to a high-utilization split phase, and bucket files began streaming
  to disk during execution instead of only becoming visible at the end
- LoRA bucket continuation now keeps the original base model and chains the
  previous bucket checkpoint through `adapters`, which avoids treating a LoRA
  checkpoint as a standalone base model
- patched native `ms-swift` now also supports `teacher_data_mode: offline_topk`
  and `swift sample --sampler_type gkd_topk`
- the control-plane runtime precheck is now conditional:
  native GKD with `teacher_model_server` still requires `vllm`, but
  `offline_topk` GKD does not

Current RL smoke status for MemoryGym:

- ORBIT now contains a profile-based native `ms-swift` GRPO smoke config for
  MemoryGym under
  `examples/official/training/targon-qwen3-8b-memorygym-grpo-smoke.yaml`
- the launch surface now resolves through the internal RL package split:
  - `packages/rl_runtime`
  - `packages/affine_ms_swift`
  - `packages/env_memorygym`
- `packages/affine_ms_swift` now also owns the local fork source tree under
  `packages/affine_ms_swift/vendor/ms_swift_fork`
- the current runtime path still uses the normal `training_launch` flow and the
  thin `scripts/memorygym_ms_swift_plugin.py` shim as a migration layer
- real validation records now exist under
  `logs/real-tests/memorygym-8b-profile-20260410/`
- the first profile-based run failed because the env-pack package itself was not
  staged to the rental, which surfaced as
  `ModuleNotFoundError: orbit_env_memorygym`
- rerunning the original launch command after staging `packages/env_memorygym`
  fixed that issue and reached:
  - remote runtime precheck
  - MemoryGym package install
  - env-pack install
  - rollout model prefetch
  - live `swift rollout` startup
  - live `swift rlhf` startup
- the current blocker is still upstream `ms-swift` server-mode external-vLLM
  communicator initialization:
  `RuntimeError: NCCL error: invalid usage`
- a subsequent real validation run confirmed that training bundles now stage and
  prefer the in-repo `ms-swift` fork:
  remote precheck logged
  `swift runtime import ok: version=4.0.4 path=/root/orbit-execution/.../bundle/inputs/runtime-swift-fork-ms_swift_fork/swift/__init__.py`
- the remote `swift rollout` command path also resolved into that staged fork
- therefore the new profile-based MemoryGym path is partially real-validated
  but not yet a successful supported workflow
- the consolidated issue and reproduction register for the current MemoryGym RL
  debugging effort lives at:
  `logs/real-tests/RL_BLOCKERS_AND_REPROS.md`

Public release validation now also has a dedicated automated path:

- the private repo workflow `publish-public.yml` builds a public snapshot from
  `release/public-export.yaml`
- the exported snapshot now includes `packages/` because public validation and
  the public Docker image consume those package sources directly
- validation is executed against the exported snapshot, not the private source
  tree
- the workflow reruns the original failure modes that previously broke public
  releases:
  - `python -m orbit control --help`
  - the focused pytest/control/execution validation inside the exported tree
  - `lychee README.md docs`
- only after those checks pass does the workflow push to
  `AffineFoundation/ORBIT`
- after push, the workflow waits for public `CI`, `Docs`, and `Docker` runs on
  the published commit
- the private `Docker` and `publish-public` workflows now also auto-trigger on
  `packages/**` changes so package-boundary edits cannot bypass image or public
  snapshot validation

Key runtime fixes that are now covered by tests:

- local teacher models and teacher adapters are staged into training bundles
  through explicit YAML placeholders
- `swift_passthrough` forwards unmodeled upstream `ms-swift` flags without
  breaking modeled config fields
- large local training datasets on Targon launches can be staged to
  `HF_RUNTIME_REPO` and downloaded directly on the rental instead of being
  copied into the SSH bundle
- experiment persistence uses a lock plus atomic replace so concurrent control
  workflows do not corrupt experiment YAML
- native GKD training bundles now fail early with a clear runtime precheck if
  `vllm` is missing instead of surfacing a late `swift` import error
- offline-topk GKD training bundles now omit the `vllm` runtime requirement and
  persist the offline field names in effective config
- training-launch experiment persistence now distinguishes:
  - top-level `train_config` as effective config
  - `results.extra.training_launch_config_declared` as raw launch declaration
  - `results.extra.training_launch_config_resolved` as launcher-derived config
  - `results.extra.training_bucket_plan_resolved` as per-stage bucket configs

## Documentation Rule

When updating testing docs, always record:

- exact commands run
- current result
- required external dependencies
- whether a failure is a code defect or an environment prerequisite
