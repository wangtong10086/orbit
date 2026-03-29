# Refactor Progress

This file is the live execution log for the control-plane / execution-plane refactor.

## Overview

| Milestone | Status | Primary deliverable | Last reviewed commit | Next gate |
|---|---|---|---|---|
| EX0 | in_progress | Docs and architecture pivot to control plane + execution plane | `working-tree` | Review rewritten docs and architecture rules |
| EX1 | in_progress | Execution contracts, bundles, and `forge worker render` | `working-tree` | Expand tests and validate bundle-first path |
| EX2 | in_progress | Docker runtime for local development and smoke tests | `working-tree` | Run real train / eval / collect bundles on Docker |
| EX3 | planned | Real task renderers for train / eval / collect | `n/a` | Verify bundles call real business entrypoints |
| EX4 | planned | Targon and SSH runtimes over the same bundle format | `n/a` | Real remote validation on isolated machines |
| EX5 | planned | Legacy execution-path demotion and cleanup | `n/a` | Remove direct runtime coupling from old paths |
| EX6 | planned | Dockerfile and deployment image consolidation | `n/a` | Freeze image build workflow from dev exploration |
| CP0 | in_progress | Control-plane experiment registry and `forge control` CLI | `working-tree` | Review new control package and root CLI migration |
| CP1 | in_progress | Control-plane training submission and run tracking | `working-tree` | Validate `submit-train` / `run-status` / `collect-run` flows |
| CP2 | in_progress | Control-plane eval and collect submission | `working-tree` | Validate `submit-eval` / `submit-collect-navworld` and task-scoped run queries |
| CP3 | in_progress | Agents orchestrate through the control plane | `working-tree` | Verify `TrainerAgent` and `EvolutionLoop` no longer launch through direct runtime paths |

## Status Legend

- `planned`
- `in_progress`
- `in_review`
- `passed`
- `committed`
- `blocked`

## Current Direction

The active refactor no longer treats the entire system as a single three-layer runtime.

Current target:

- control plane at the system level
- execution plane at the system level
- three-layer `Foundation / Pipelines / Agents` retained inside the future control plane

The current implementation focus is:

- execution-plane-first foundations already landed
- control-plane reconstruction has now started on top of those foundations

## EX0 — Docs and Architecture Pivot

**Status:** `in_progress`

**Goal**

Rewrite the active refactor docs and architecture guidance to target a control-plane / execution-plane split.

**Scope**

- rewrite `docs/refactor/roadmap.md`
- rewrite `docs/refactor/progress.md`
- rewrite `docs/refactor/real-test-plan.md`
- update `docs/architecture-zh.md`
- add execution-plane documents
- update `AGENTS.md`

**Progress snapshot**

- execution-plane code has started landing in the working tree under `forge/execution/`
- `forge worker` is now registered in the root CLI
- roadmap and progress rewrite are in the current working tree

**Review checklist**

- control plane and execution plane are both explicitly defined
- three-layer trunk is scoped to the control plane, not the whole system
- bundle-first and runtime-only rules are documented
- docs do not claim the control layer has already been implemented

**Test checklist**

- `uv run forge --help`
- verify `worker` appears in the root CLI
- verify new documentation files exist and are indexed

**Open issues / next step**

- finish documentation rewrite and index updates
- move EX0 to `in_review` after docs are internally consistent

## EX1 — Execution Contracts + Bundle

**Status:** `in_progress`

**Goal**

Introduce the execution-plane contract set, local bundle layout, and the first `forge worker` rendering commands.

**Scope**

- `forge/execution/contracts.py`
- `forge/execution/bundle.py`
- `forge/execution/renderers.py`
- `forge/cli_worker.py`
- root CLI registration

**Implemented in the working tree**

- `forge/execution/` exists
- bundle layout is defined with:
  - `job.json`
  - `inputs/`
  - `scripts/entrypoint.sh`
  - `artifacts/manifest.json`
  - `runtime/`
- `forge worker render train`
- `forge worker render eval`
- `forge worker render collect-navworld`
- `forge worker validate-bundle`

**Review checklist**

- task renderers do not contain Targon or SSH launch logic
- bundle validation is separate from runtime launch
- execution contracts are independent from the current training provider surface
- root CLI exposes `worker` as a first-class family

**Test checklist**

- `./.venv/bin/python -m compileall forge/execution forge/cli_worker.py forge/cli.py`
- `uv run forge worker --help`
- `uv run forge worker render train ...`
- `uv run forge worker render eval ...`
- `uv run forge worker render collect-navworld ...`
- `uv run forge worker validate-bundle ...`
- `./.venv/bin/python -m pytest -q tests/test_execution.py tests/test_cli.py`

**Current test record**

- `./.venv/bin/python -m compileall forge/execution forge/cli_worker.py forge/cli.py`
  - Result: pass
- `uv run forge worker --help`
  - Result: pass
- local render + validate smoke:
  - train bundle: pass
  - eval bundle: pass
  - collect bundle: pass
- `./.venv/bin/python -m pytest -q tests/test_execution.py tests/test_cli.py`
  - Result: pass, 19 tests

**Open issues / next step**

- add runtime-backed smoke beyond render-only coverage
- complete EX2 Docker runtime validation before claiming execution-plane usability

## EX2 — Docker Runtime

**Status:** `in_progress`

**Goal**

Make Docker the default development runtime for execution-plane tasks.

**Exit criteria**

- `forge worker run <bundle> --runtime docker`
- `forge worker status`
- `forge worker logs`
- `forge worker collect`
- `forge worker terminate`
- one minimal train bundle runs in Docker
- one minimal eval bundle runs in Docker
- one minimal collect bundle runs in Docker

**Current evidence in the working tree**

- Docker runtime implementation exists in `forge/execution/runtimes.py`
- foreground Docker run now writes `runtime/result.json`
- `forge worker logs` now falls back to local artifact logs after foreground `--rm` runs
- a self-contained synthetic bundle was executed successfully with:
  - `uv run forge worker run tmp/bundle-runtime-smoke --runtime docker --foreground --image python:3.12-slim`
  - followed by:
    - `uv run forge worker status tmp/bundle-runtime-smoke`
    - `uv run forge worker logs tmp/bundle-runtime-smoke --tail 20`
    - `uv run forge worker collect tmp/bundle-runtime-smoke`

**Open issues / next step**

- synthetic self-contained Docker smoke is passing
- real Docker business-bundle progress:
  - NAVWORLD collect bundle is now passing on Docker:
    - render:
      - `uv run forge worker render collect-navworld --bundle-dir tmp/bundle-collect-real --job-id collect-real -n 1 --overwrite`
    - run:
      - `uv run forge worker run tmp/bundle-collect-real --runtime docker --foreground --image qqr:eval-base`
    - follow-up:
      - `uv run forge worker status tmp/bundle-collect-real`
      - `uv run forge worker logs tmp/bundle-collect-real --tail 80`
      - `uv run forge worker collect tmp/bundle-collect-real`
    - outcome:
      - Docker run completed with `state=succeeded`
      - bundle logs show one real NAVWORLD sample was generated
      - `artifacts/navworld_synthetic.jsonl` was collected into the bundle manifest
- real Docker `eval` bundle validation is still pending
- local Docker `train` bundle validation remains limited by the absence of a local GPU environment
- runtime reality check:
  - the actively proven remote runtime is currently Targon
  - Docker is still useful as a local development harness, but not the primary execution target for closeout
- base-image exploration and dependency capture must be folded into `docs/operations.md` or the dated real-test reports under `logs/real-tests/`
- Targon train bundle smoke has also been exercised through the new execution plane:
  - render:
    - `uv run forge worker render train tmp/train_min.jsonl --bundle-dir tmp/bundle-train-targon --job-id targon-train-smoke --model Qwen/Qwen2.5-0.5B-Instruct --epochs 1 --batch-size 1 --max-length 1024 --overwrite`
  - run:
    - `uv run forge worker run tmp/bundle-train-targon --runtime targon --profile bootstrap --dataset-repo monokoco/affine-sft-data --gpu-type H200`
  - status:
    - `uv run forge worker status tmp/bundle-train-targon`
  - logs:
    - `uv run forge worker logs tmp/bundle-train-targon --tail 120`
  - outcome:
    - run `wrk-mvmb265gz2w7` reached `state=running`
    - logs show bootstrap progressing through package installation
    - workload was terminated after verification to avoid unnecessary spend
- Targon collect bundle smoke has also been exercised through the new execution plane:
  - render:
    - `uv run forge worker render collect-navworld --bundle-dir tmp/bundle-collect-targon --job-id collect-targon -n 1 --overwrite`
  - run:
    - `uv run forge worker run tmp/bundle-collect-targon --runtime targon --profile bootstrap --dataset-repo monokoco/affine-sft-data --gpu-type H200`
  - status:
    - `uv run forge worker status tmp/bundle-collect-targon`
  - logs:
    - `uv run forge worker logs tmp/bundle-collect-targon --tail 120`
  - outcome:
    - run `wrk-pxw9vp74gxty` reached `state=running`
    - logs show bootstrap progressing through package installation
    - workload was terminated after verification to avoid unnecessary spend
- Targon eval bundle smoke has also been exercised through the new execution plane:
  - render:
    - `uv run forge worker render eval --bundle-dir tmp/bundle-eval-targon --job-id eval-targon --model Qwen/Qwen3-32B-TEE --envs GAME --samples 1 --base-url https://llm.chutes.ai/v1 --affinetes-dir /workspace/affinetes --overwrite`
  - run:
    - `uv run forge worker run tmp/bundle-eval-targon --runtime targon --profile bootstrap --dataset-repo monokoco/affine-sft-data --gpu-type H200`
  - status:
    - `uv run forge worker status tmp/bundle-eval-targon`
  - logs:
    - `uv run forge worker logs tmp/bundle-eval-targon --tail 200`
  - outcome:
    - run `wrk-50q5mbvuzzp3` reached `state=running`
    - logs show bootstrap progressing through dependency installation for the eval bundle
    - the eval bundle uses a real external OpenAI-compatible endpoint at `https://llm.chutes.ai/v1`
    - workload was terminated after verification to avoid unnecessary spend

## EX3 — Real Task Renderers

**Status:** `planned`

**Goal**

Ensure train / eval / collect bundles all call the real business entrypoints already present in the repo.

**Exit criteria**

- train bundle uses real `SwiftConfig`
- eval bundle uses the real evaluation script path
- collect bundle uses the real data collection path

## EX4 — Targon and SSH Runtimes

**Status:** `planned`

**Goal**

Run the same bundle format on remote runtimes.

**Exit criteria**

- Targon runtime works for at least one real train bundle
- SSH runtime works for at least one real train bundle
- both can report status, logs, and collect artifacts
- all remote validation uses isolated rental machines where required

## EX5 — Legacy Execution Cleanup

**Status:** `planned`

**Goal**

Demote the old provider path and make `forge worker` the recommended runtime-facing interface.

**Exit criteria**

- old runtime-facing path is documented as compatibility only
- task renderers and runtimes own the new execution path

## EX6 — Deployment Image Freeze

**Status:** `planned`

**Goal**

Freeze the stable Docker workflow into real Dockerfiles and deployment docs.

**Exit criteria**

- development exploration is reflected in a stable Dockerfile
- deployment image and development image share the same worker entrypoint

## CP0 — Control-Plane Registry and CLI

**Status:** `in_progress`

**Goal**

Introduce an explicit control-plane package and replace the old experiment-only CLI surface.

**Scope**

- `forge/control/`
- `forge/cli_control.py`
- root CLI migration from `exp` to `control`
- experiment storage migration out of `forge/pipeline/`

**Current evidence in the working tree**

- `forge/control/experiment.py` defines `Experiment` and `ExperimentStore`
- `forge/control/service.py` defines `ControlPlane`
- `forge control` is now the active root-level control-plane command family
- `forge/cli_exp.py` and `forge/pipeline/experiment.py` have been removed from the active path

**Review checklist**

- control-plane experiment storage is no longer implemented under `forge/pipeline/`
- root CLI no longer registers `exp`
- new control service depends on execution-plane contracts, not legacy providers
- agent and tests import experiment state from `forge/control/`

**Test checklist**

- `uv run forge --help`
- `uv run forge control --help`
- `./.venv/bin/python -m pytest -q tests/test_control.py tests/test_cli.py tests/test_agent.py tests/test_pipeline.py tests/test_training.py`

**Current test record**

- `uv run forge --help`
  - Result: pass, root CLI now lists `control`
- `uv run forge control --help`
  - Result: pass
- `./.venv/bin/python -m pytest -q tests/test_control.py tests/test_cli.py tests/test_agent.py tests/test_pipeline.py tests/test_training.py`
  - Result: pass, 97 tests
- manual CLI smoke:
  - `uv run forge control --dir tmp/control-smoke create --id v-smoke --variable improve_navworld --hypothesis smoke --train-config '{"model":"Qwen/Qwen3-32B","learning_rate":0.0001,"lora_rank":64,"max_length":4096,"num_train_epochs":1,"output_dir":"/tmp/checkpoints"}' --data-config '{"GAME":{"count":100}}'`
  - `uv run forge control --dir tmp/control-smoke render-train v-smoke tmp/control-smoke-train.jsonl --bundle-dir tmp/control-bundle-smoke`
  - `uv run forge control --dir tmp/control-smoke show v-smoke --json`
  - Result: pass, experiment state moved to `prepared` and recorded `training_run.bundle_path`

**Open issues / next step**

- move CP0 toward `in_review` after a dedicated doc review pass

## CP1 — Control-Plane Training Submission

**Status:** `in_progress`

**Goal**

Make the control plane responsible for high-level training submission and run tracking over the execution plane.

**Scope**

- `ControlPlane.render_training_bundle`
- `ControlPlane.submit_training`
- `ControlPlane.refresh_run_status`
- `ControlPlane.read_run_logs`
- `ControlPlane.collect_run_artifacts`
- `forge control render-train`
- `forge control submit-train`
- `forge control run-status`
- `forge control run-logs`
- `forge control collect-run`

**Current evidence in the working tree**

- control-plane training submission now composes `TrainingPipeline` + `RuntimeBackend`
- run handles, status, and manifest data are persisted back into experiment results
- control-plane CLI can render, submit, inspect, and collect training runs without using a legacy `train` command family

**Review checklist**

- control-plane service does not import Targon or SSH implementation details directly
- control-plane training submission goes through execution runtimes
- run metadata is stored in experiment state rather than hidden in CLI glue
- no removed legacy execution surface was reintroduced

**Test checklist**

- `./.venv/bin/python -m pytest -q tests/test_control.py tests/test_cli.py tests/test_agent.py tests/test_training.py`
- representative manual CLI smoke with:
  - `forge control create`
  - `forge control render-train`
  - `forge control submit-train`

**Current test record**

- `./.venv/bin/python -m pytest -q tests/test_control.py tests/test_cli.py tests/test_agent.py tests/test_training.py`
  - Result: pass, 85 tests
- real control-plane runtime smoke:
  - `uv run forge control --dir tmp/control-runtime-smoke create --id v-runtime-smoke --variable runtime_control --hypothesis 'control plane can drive targon runtime' --train-config '{"model":"Qwen/Qwen2.5-0.5B-Instruct","learning_rate":0.0001,"lora_rank":64,"max_length":1024,"num_train_epochs":1,"per_device_train_batch_size":1,"gradient_accumulation_steps":1,"num_gpus":1,"output_dir":"/tmp/checkpoints"}' --data-config '{"GAME":{"count":1}}'`
  - `uv run forge control --dir tmp/control-runtime-smoke submit-train v-runtime-smoke tmp/control-runtime-smoke/train.jsonl --runtime targon --profile bootstrap --dataset-repo monokoco/affine-sft-data --gpu-type H200 --bundle-dir tmp/control-runtime-smoke/bundle-train`
  - `uv run forge control --dir tmp/control-runtime-smoke run-status v-runtime-smoke`
  - `uv run forge control --dir tmp/control-runtime-smoke run-logs v-runtime-smoke --tail 80`
  - `uv run forge control --dir tmp/control-runtime-smoke terminate-run v-runtime-smoke`
  - `uv run forge control --dir tmp/control-runtime-smoke show v-runtime-smoke --json`
  - Result: pass, control plane submitted real Targon runs `wrk-jtqkyk7aeixv` and `wrk-v6bw9ri2jmih`, inferred runtime for follow-up commands, observed `state=running`, retrieved bootstrap logs, and moved the experiment to `status=terminated`

**Open issues / next step**

- later phases should expand the control plane beyond train-only submission

## CP2 — Control-Plane Eval and Collect Submission

**Status:** `in_progress`

**Goal**

Make the control plane capable of submitting and tracking eval and collect work in addition to training.

**Scope**

- `ControlPlane.render_eval_bundle`
- `ControlPlane.submit_eval`
- `ControlPlane.render_collect_navworld_bundle`
- `ControlPlane.submit_collect_navworld`
- task-scoped run lookup for `run-status`, `run-logs`, `collect-run`, and `terminate-run`

**Current evidence in the working tree**

- control-plane service now records separate `training_run`, `evaluation_run`, and `collect_run` entries under experiment results
- `forge control` now exposes:
  - `render-eval`
  - `submit-eval`
  - `render-collect-navworld`
  - `submit-collect-navworld`
- `forge control run-status/run-logs/collect-run/terminate-run` now accept `--task train|eval|collect`

**Review checklist**

- control-plane task methods still delegate execution to runtime backends
- eval and collect bundle generation remains in the execution plane
- run records for different task kinds do not overwrite each other
- control CLI remains the only public control-side task submission surface

**Test checklist**

- `uv run forge control --help`
- `./.venv/bin/python -m pytest -q tests/test_control.py tests/test_cli.py`
- manual CLI smoke with:
  - `forge control render-eval`
  - `forge control render-collect-navworld`

**Current test record**

- `uv run forge control --help`
  - Result: pass, eval and collect commands are listed
- `./.venv/bin/python -m pytest -q tests/test_control.py tests/test_cli.py`
  - Result: pass, 26 tests
- manual CLI smoke:
  - `uv run forge control --dir tmp/control-smoke render-eval v-smoke --model Qwen/Qwen2.5-0.5B-Instruct --envs GAME --bundle-dir tmp/control-bundle-eval`
  - `uv run forge control --dir tmp/control-smoke render-collect-navworld v-smoke -n 1 --bundle-dir tmp/control-bundle-collect`
  - `uv run forge control --dir tmp/control-smoke show v-smoke --json`
  - Result: pass, experiment state records `evaluation_run.bundle_path` and `collect_run.bundle_path`
- runtime inference coverage:
  - `run-status`, `run-logs`, `collect-run`, and `terminate-run` can now infer runtime from the stored run handle instead of requiring `--runtime`
- real non-train runtime smoke:
  - `uv run forge control --dir tmp/control-final-smoke submit-collect-navworld v-collect-final --runtime targon -n 1 --profile bootstrap --dataset-repo monokoco/affine-sft-data --gpu-type H200 --bundle-dir tmp/control-final-smoke/bundle-collect`
  - `uv run forge control --dir tmp/control-final-smoke run-status v-collect-final --task collect`
  - `uv run forge control --dir tmp/control-final-smoke run-logs v-collect-final --task collect --tail 60`
  - `uv run forge control --dir tmp/control-final-smoke terminate-run v-collect-final --task collect`
  - `uv run forge control --dir tmp/control-final-smoke show v-collect-final --json`
  - Result: pass, real Targon collect run `wrk-5yfe6ymxsnaj` reached `running`, logs were readable, follow-up commands inferred runtime, and experiment top-level status remained `draft`

**Open issues / next step**

- later phases can attach richer evaluation result ingestion through the control plane

## CP3 — Agents Through the Control Plane

**Status:** `in_progress`

**Goal**

Move agent-side task execution onto the control plane so that agents stop talking to execution runtimes and training launch paths directly.

**Scope**

- `TrainerAgent`
- control-plane-backed experiment persistence from agents
- `EvolutionLoop` coverage through a control-plane-backed trainer

**Current evidence in the working tree**

- `TrainerAgent` now submits training through `ControlPlane.submit_training(...)`
- agent execution persists `training_run` into experiment state through the control plane
- when evaluation is available, trainer agent now records `agent_eval` back into experiment results
- existing `EvolutionLoop` tests pass with the control-plane-backed trainer path

**Review checklist**

- agent code no longer launches training by calling `TrainingPipeline.launch(...)` directly
- agent code no longer talks to execution runtimes except through the control plane
- experiment state is updated through control-plane persistence, not ad hoc agent-side file writes
- blocked / launched / completed semantics stay explicit

**Test checklist**

- `./.venv/bin/python -m pytest -q tests/test_agent.py tests/test_control.py tests/test_training.py`
- `./.venv/bin/python -m pytest -q`

**Current test record**

- `./.venv/bin/python -m pytest -q tests/test_agent.py tests/test_control.py tests/test_cli.py tests/test_training.py`
  - Result: pass, 85 tests
- `./.venv/bin/python -m pytest -q`
  - Result: pass, 175 tests

**Open issues / next step**

- extend agent-side use of the control plane beyond training submission, especially around richer eval ingestion and future control-side task policies
