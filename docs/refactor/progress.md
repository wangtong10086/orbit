# Refactor Progress

This file is the execution log for the active refactor. It records milestone status, review outcomes, test outcomes, and commit gates.

## Overview

| Milestone | Status | Primary deliverable | Last reviewed commit | Next gate |
|---|---|---|---|---|
| M0 | committed | Refactor governance docs in `docs/refactor/` | `ee3f4fd` | Start M1 |
| M1 | committed | Foundation contracts and `EnvironmentCatalog` | `3bd074a` | Start M2 |
| M2 | committed | Data usable path and packer ownership | `9666425` | Start M3 |
| M3 | committed | Unified training path and execution providers | `16065ab` | Start M4 |
| M4 | committed | Real evaluation path and strict scoring | `ca3af65` | Start M5 |
| M5 | committed | Thin agents over real pipelines | `58b1cc1` | Start M6 |
| M6 | committed | CLI reorganization and sidecar convergence | `b78c399` | Refactor roadmap complete |

## Status Legend

- `planned`
- `in_progress`
- `in_review`
- `blocked`
- `passed`
- `committed`

## Milestone Update Rules

- When a milestone begins, set status to `in_progress`.
- When formal milestone review starts, set status to `in_review`.
- If review or testing fails, record the failure and return the milestone to `in_progress`.
- When review and testing both pass, set status to `passed`.
- Only after the passing commit is created and recorded may the milestone move to `committed`.
- Do not write "done" without review outcome, test outcome, and commit record.

## M0 — Governance Skeleton

**Status:** `committed`

**Goal**

Establish the governance documentation system for the refactor and define the mandatory execution gates for all later milestones.

**Scope**

- Create `docs/refactor/README.md`
- Create `docs/refactor/roadmap.md`
- Create `docs/refactor/progress.md`
- Define milestone structure and gate rules
- Mark `docs/refactor/` as the active source of truth for this refactor

**Out of scope**

- Any production code refactor
- CLI changes
- Contract implementation
- Migration of historical content into the new files

**Exit criteria**

- All three governance documents exist and are internally consistent
- The active source-of-truth policy is clearly stated
- M0 through M6 milestones are defined
- Review, test, and commit gates are documented in reusable form

**Implementation notes**

- Initial governance documents are being created in the current working tree.
- Historical files under `docs/` are intentionally preserved and not rewritten in M0.
- This milestone establishes process only; implementation work starts in later milestones.
- `AGENTS.md` is also being introduced as the execution charter for later refactor tasks without becoming a second status source.

**Review checklist**

- [x] `docs/refactor/README.md` is navigation-only and does not duplicate roadmap/progress detail
- [x] `docs/refactor/roadmap.md` contains long-lived architecture and governance decisions only
- [x] `docs/refactor/progress.md` contains milestone execution state only
- [x] Source-of-truth language is explicit and unambiguous
- [x] Gate rules are usable for every future milestone

**Review notes**

- Layer boundaries are documented only in `roadmap.md`; `README.md` remains navigation-only and `progress.md` remains execution-only.
- `AGENTS.md` points all future refactor execution back to `docs/refactor/` and does not introduce a second status source.
- No production code or compatibility path was introduced in M0; this milestone stayed governance-only as intended.

**Test checklist**

- [x] Confirm all three files exist under `docs/refactor/`
- [x] Confirm links in `README.md` resolve correctly
- [x] Confirm milestone table includes M0 through M6
- [x] Confirm allowed status values are documented
- [x] Confirm `AGENTS.md` exists at the repository root and points future work back to `docs/refactor/`

**Test record**

- Commands:
  - `rg --files docs/refactor AGENTS.md`
  - `ls -l docs/refactor/README.md docs/refactor/roadmap.md docs/refactor/progress.md AGENTS.md`
  - `python - <<'PY' ...` to verify file existence, README link targets, milestone rows, and documented status values
- Result summary:
  - All governance files exist in the expected locations.
  - README link targets resolve.
  - M0 through M6 are present in the overview table.
  - Allowed status values are documented.
  - `AGENTS.md` exists at repo root and correctly delegates live state to `docs/refactor/`.
- Failures / gaps:
  - None for M0 scope.
- Exit criteria:
  - Satisfied.

**Gate result**

- Review: pass
- Test: pass
- Result: milestone passed and was committed as `ee3f4fd`

**Commit record**

- Passing commit: `ee3f4fd` (`docs: establish refactor governance skeleton`)

**Open issues / next step**

- Start M1 from the explicit environment catalog and scoring policy boundary.
- Keep all further work inside M1 until its own review and test gates pass.

## M1 — Foundation Contracts + Catalog

**Status:** `committed`

**Goal**

Define the core foundation contracts and replace implicit environment registration with explicit catalog wiring.

**Scope**

- Introduce core contracts
- Introduce `EnvironmentCatalog`
- Remove import side effect environment registration
- Define strict scoring policy as a single source of truth

**Out of scope**

- Data pipeline migration beyond what is required for contract definition
- Training provider implementation
- CLI restructuring

**Exit criteria**

- Core contracts exist and are documented
- Environment discovery is explicit
- Import side effect registration is removed from the active path
- Strict scoring semantics are documented and implemented in the foundation layer

**Implementation notes**

- Active slice started after M0 commit `ee3f4fd`.
- Added `forge.foundation.environment_catalog.EnvironmentCatalog` as the explicit built-in composition root for environment discovery.
- Removed import-triggered registration from built-in environment modules; `EnvRegistry` and `EnvHub` now act as compatibility wrappers over the explicit catalog instead of being the active source of truth.
- Added `forge.foundation.scoring.ScoringPolicy.strict_geo_mean` and switched active pipeline/agent geometric-mean calculations to that single implementation.
- Updated tests to prove the built-in catalog works without side-effect registration imports and to enforce zero-score behavior in geometric mean calculations.
- Added `forge.foundation.contracts` with explicit Protocol/dataclass boundaries for `TrainingSpec`, `EvaluationSpec`, `ExecutionProvider`, `ArtifactStore`, `CanonicalRepository`, `ConversationPacker`, and `EvaluationRunner`.
- Updated `TrainerAgent` and `Evaluator` to consume the new training/evaluation contracts instead of leaving those request shapes implicit inside agent logic.
- Slimmed `forge.foundation` and `forge.env` package exports to lazy resolution so the explicit catalog can be imported without package-init cycles.

**Review checklist**

- [x] No hidden global registration remains in the active architecture path
- [x] Contracts are explicit and composition-friendly
- [x] Scoring semantics match documented leaderboard rules

**Review notes**

- Active environment discovery now flows through `forge.foundation.environment_catalog.EnvironmentCatalog`; built-in environment modules are no longer discovered by import side effects.
- `EnvRegistry` and `EnvHub` remain only as compatibility wrappers over the explicit catalog. No active pipeline or agent path introduced in M1 depends on decorator registration order.
- Foundation boundaries now exist as explicit `Protocol`/dataclass contracts in `forge.foundation.contracts`, with training/evaluation request shapes pulled out of agent internals.
- Core geometric-mean calculation is centralized in `forge.foundation.scoring.ScoringPolicy.strict_geo_mean`; active pipeline and agent code no longer carry their own independent implementations.
- Refactor source-of-truth docs now explicitly define strict scoring semantics as unsmoothed geometric mean with zero forcing the result to zero. Older knowledge notes that discuss epsilon smoothing remain historical/external analysis and are not used as architecture authority for the refactor.

**Test checklist**

- [x] Catalog construction works without side-effect imports
- [x] Scoring tests cover zero-score behavior

**Test record**

- Commands:
  - `pytest tests/test_env.py tests/test_pipeline.py tests/test_agent.py`
  - `python -m compileall forge/foundation forge/env forge/pipeline forge/agent forge/data`
  - `pytest tests/test_foundation.py tests/test_env.py tests/test_pipeline.py tests/test_agent.py`
  - `python -m compileall forge/foundation forge/env forge/pipeline forge/agent tests`
  - `pytest`
  - `python -m compileall forge tests`
- Result summary:
  - Initial explicit-catalog and strict-scoring slice passed 100 tests.
  - Foundation-contract slice passed 109 tests after package-init cycle removal.
  - Full repository test suite passed: 166 tests.
  - Python compilation checks passed for all touched modules and for the full `forge` package plus tests.
- Failures / gaps:
  - An initial import cycle between `forge.foundation` and `forge.env` was found during `tests/test_foundation.py` collection and fixed by making both package exports lazy.
  - A stale training test expected the old `swift sft <yaml>` form; it was aligned with the actual `swift sft --config <yaml>` interface used by the current code.
  - No additional functional failures remain in the tested repository suite.
- Exit criteria:
  - Satisfied.

**Gate result**

- Review: pass
- Test: pass
- Result: milestone passed and was committed as `3bd074a`.

**Commit record**

- Passing commit: `3bd074a` (`refactor: finalize foundation catalog milestone`)

**Open issues / next step**

- Start M2 from canonical repository and conversation packer ownership.
- Keep future work focused on the real ingest/dataset build path; do not reopen M1 compatibility concerns unless a new hidden registry or duplicate scoring path appears.

## M2 — Data Usable Path

**Status:** `committed`

**Goal**

Build a real data ingest and dataset-build path with packers owned by the data path rather than CLI glue.

**Scope**

- `CanonicalRepository`
- `ConversationPacker`
- `DataIngestPipeline`
- `DatasetBuildPipeline`

**Out of scope**

- Agent rewiring
- CLI reorganization beyond temporary callsites needed for the path

**Exit criteria**

- Canonical ingest is repository-backed
- Dataset build is pipeline-backed
- model-specific packing is owned by packers, not CLI modules

**Implementation notes**

- Active slice started after M1 commit `3bd074a`.
- Added `forge.foundation.repository.LocalCanonicalRepository` as the concrete implementation of the `CanonicalRepository` contract for local canonical JSONL storage.
- Added `forge.foundation.packing.Qwen3ConversationPacker` and `IdentityConversationPacker` so model-specific message shaping now lives below CLI modules.
- Added `DataIngestPipeline` and `DatasetBuildPipeline` in `forge.pipeline.data`.
- Updated canonical ingest helpers to preserve canonical message structure and delegate active append behavior to the repository-backed ingest pipeline.
- Updated dataset build helpers and CLI entrypoints to build training files from the local canonical repository through `DatasetBuildPipeline` instead of ad hoc merge logic.
- Updated rental data preparation to reuse the shared Qwen3 packer instead of embedding tool-call normalization logic in the CLI module.

**Review checklist**

- [x] Data path is repository-driven instead of in-memory placeholder state
- [x] Packers own environment/model-specific shaping logic
- [x] CLI modules do not own conversation normalization logic

**Review notes**

- Canonical storage now has an explicit concrete repository implementation in `forge.foundation.repository.LocalCanonicalRepository`; active ingest and dataset-build paths no longer depend on ad hoc file handling inside CLI code.
- `DataIngestPipeline` is now the active append path for canonical data, and deduplication is computed against repository state rather than an in-memory batch store.
- Model-specific packing now lives in `forge.foundation.packing.Qwen3ConversationPacker`; it owns tool-call XML conversion, tool-response wrapping, and tool-schema preamble injection.
- `forge.data.canonical_ops.normalize_entry` now limits itself to canonical-schema sanitation and no longer performs Qwen3-specific packing.
- `forge.cli_data.aggregate` and `forge.cli_rental.prepare-data` now reuse the shared repository/pipeline/packer path instead of embedding conversation-normalization policy in CLI modules.

**Test checklist**

- [x] Ingest path covers dedup against existing canonical data
- [x] Dataset build covers LIVEWEB/NAVWORLD packing

**Test record**

- Commands:
  - `pytest tests/test_foundation.py tests/test_pipeline.py tests/test_agent.py tests/test_env.py`
  - `python -m compileall forge/foundation forge/pipeline forge/data forge/cli_data.py forge/cli_rental.py tests`
  - `pytest`
  - `python -m compileall forge tests`
- Result summary:
  - Added repository and packer tests passed, including dedup against existing canonical data and Qwen3 packing of tool-call conversations.
  - Full repository test suite passed: 170 tests.
  - Python compilation checks passed for touched modules and for the full `forge` package plus tests.
- Failures / gaps:
  - None remaining in the tested path.
- Exit criteria:
  - Satisfied.

**Gate result**

- Review: pass
- Test: pass
- Result: milestone passed and was committed as `9666425`.

**Commit record**

- Passing commit: `9666425` (`refactor: build repository-backed data pipeline`)

**Open issues / next step**

- Start M3 from unified training orchestration and explicit execution providers.
- Keep model-specific packing in `forge.foundation.packing`; do not reintroduce chat-template shaping into CLI modules.

## M3 — Training Usable Path

**Status:** `committed`

**Goal**

Unify the training execution path around a single pipeline and explicit execution providers.

**Scope**

- `TrainingPipeline`
- `SshExecutionProvider`
- `TargonBootstrapProvider`
- `TargonImageProvider`

**Out of scope**

- Agent-level decision logic
- Full CLI convergence

**Exit criteria**

- Training orchestration has one active path
- Targon modes are separate providers
- old runner/executor dual path is removed

**Implementation notes**

- Active slice started after M2 commit `9666425`.
- Added `forge.pipeline.training.TrainingPipeline` as the single active orchestration entrypoint for training launches.
- Added explicit providers in `forge.training.providers`: `SshExecutionProvider`, `TargonBootstrapProvider`, and `TargonImageProvider`.
- Split Targon operation into two explicit modes:
  - `TargonBootstrapProvider` uses the official base image and bootstraps ms-swift at launch time.
  - `TargonImageProvider` assumes a prebuilt image and injects only runtime artifacts plus configuration.
- Updated `TrainingRunner` to become a compatibility wrapper over `TrainingPipeline` instead of carrying its own training-launch implementations.
- Updated CLI training commands to require explicit provider choice (`ssh`, `targon-bootstrap`, `targon-image`) rather than routing through an implicit generic Targon path.
- Reduced `forge.training.executor.remote` and `forge.training.executor.targon` to compatibility shims so the duplicate launch implementations are no longer active.

**Review checklist**

- [x] No duplicated training orchestration remains
- [x] Provider choice is explicit
- [x] Shared Targon control-plane code stays low-level

**Review notes**

- Active training orchestration now flows through `forge.pipeline.training.TrainingPipeline` only; `TrainingRunner` delegates to it and no longer carries independent SSH/Targon launch mechanics.
- Provider choice is explicit in code and CLI. There is no automatic fallback between bootstrap and image modes; invalid modes raise immediately.
- Targon launch mechanics are shared only in the private `_BaseTargonExecutionProvider` helper, which keeps control-plane concerns low-level while leaving mode-specific policy in `TargonBootstrapProvider` and `TargonImageProvider`.
- The old executor modules remain only as compatibility shims and no longer constitute a second active implementation path.

**Test checklist**

- [x] Training specs can target SSH and both Targon providers
- [x] Provider launch payloads and status contracts are consistent

**Test record**

- Commands:
  - `pytest tests/test_training.py tests/test_agent.py tests/test_pipeline.py tests/test_foundation.py`
  - `python -m compileall forge tests`
  - `pytest`
- Result summary:
  - Added training-pipeline/provider tests passed, covering explicit provider names, pipeline validation before launch, and rejection of unknown Targon provider modes.
  - Full repository test suite passed: 174 tests.
  - Python compilation checks passed for the full `forge` package plus tests.
- Failures / gaps:
  - None remaining in the tested M3 path.
- Exit criteria:
  - Satisfied.

**Gate result**

- Review: pass
- Test: pass
- Result: milestone passed and was committed as `16065ab`.

**Commit record**

- Passing commit: `16065ab` (`refactor: unify training execution pipeline`)

**Open issues / next step**

- Start M4 from real evaluation execution and strict scoring enforcement.
- Keep provider choice explicit; do not reintroduce generic Targon fallback paths.

## M4 — Evaluation Usable Path

**Status:** `committed`

**Goal**

Make evaluation a real execution path with one strict scoring policy.

**Scope**

- `EvaluationPipeline`
- `EvaluationRunner`
- `ScoringPolicy.strict_geo_mean`

**Out of scope**

- Agent redesign except for required integration touchpoints

**Exit criteria**

- Evaluation reports are produced by real execution
- scoring semantics are unified
- zero-score behavior matches documented rules

**Implementation notes**

- Active slice started after M3 commit `16065ab`.
- Extended `EvaluationSpec` with the execution parameters required by the real eval script: `base_url`, `output_dir`, `concurrency`, `seed`, `affinetes_dir`, `api_key`, and `skip_build`.
- Added `forge.foundation.evaluation.ScriptEvaluationRunner` to invoke `scripts/eval_envs.py`, capture its summary artifacts, and expose them through the `EvaluationRunner` contract.
- Added `EvaluationPipeline` in `forge.pipeline.eval` and moved `Evaluator` onto that real execution path as a compatibility alias.
- `EvaluationPipeline` now parses `eval_summary.json` plus per-environment `eval_<env>.json` artifacts into `EvalReport` / `EnvResult` instead of fabricating empty results.
- Per-environment scores from the eval script are normalized into percentage-scale `EnvResult.mean_score` / `scores`, while report aggregation still uses `ScoringPolicy.strict_geo_mean`.

**Review checklist**

- [x] Evaluation is not a placeholder abstraction
- [x] Scoring policy is shared across report generation and strategy logic
- [x] Documentation and implementation semantics match

**Review notes**

- Active evaluation now goes through a concrete runner that executes the repository's real eval script and consumes its produced artifacts.
- `Evaluator` no longer invents `sample_count`-only `EnvResult` placeholders. If eval artifacts exist, the report reflects real per-task scores, task IDs, sample counts, and completeness.
- Report aggregation still uses `ScoringPolicy.strict_geo_mean`, and strategist logic continues to use that same policy, so scoring semantics remain centralized.
- The documentation and implementation now align on strict scoring: evaluation reports are built from real execution outputs and aggregated via the single strict geo-mean policy.

**Test checklist**

- [x] Evaluation path returns real results
- [x] Strict geo mean tests cover empty, single, mixed, and zero-score cases

**Test record**

- Commands:
  - `pytest tests/test_foundation.py tests/test_pipeline.py tests/test_agent.py tests/test_training.py`
  - `python -m compileall forge tests`
  - `pytest`
- Result summary:
  - Added evaluation-runner/pipeline tests passed, covering script-runner parsing, real `EvalReport` population, and trainer integration through the evaluation contract.
  - Existing strict geo-mean tests remained green for empty, single, mixed, and zero-score cases.
  - Full repository test suite passed: 176 tests.
  - Python compilation checks passed for the full `forge` package plus tests.
- Failures / gaps:
  - None remaining in the tested M4 path.
- Exit criteria:
  - Satisfied.

**Gate result**

- Review: pass
- Test: pass
- Result: milestone passed and was committed as `ca3af65`.

**Commit record**

- Passing commit: `ca3af65` (`refactor: implement real evaluation pipeline`)

**Open issues / next step**

- Start M5 from agent thinning and removal of fake-success agent flows.
- Keep evaluation aggregation on `ScoringPolicy.strict_geo_mean`; do not reintroduce local scoring variants in agents or pipelines.

## M5 — Agent Thinning

**Status:** `committed`

**Goal**

Reduce agents to decision-making and orchestration over real pipelines.

**Scope**

- `StrategistAgent`
- `TrainerAgent`
- `DataAgent`
- `EvolutionLoop`

**Out of scope**

- New provider types
- New sidecar features unrelated to agent orchestration

**Exit criteria**

- Agents call real pipelines only
- fake-success placeholder flows are removed
- loop outcomes distinguish real success from blocked execution

**Implementation notes**

- Active slice started after M4 commit `ca3af65`.
- `TrainerAgent` now orchestrates `TrainingPipeline` plus `EvaluationPipeline` only. It no longer fabricates completed evaluation success when no execution provider or evaluation model path is available.
- Added `TrainingOutcome` to distinguish `blocked`, `launched`, and `completed` trainer states.
- `DataAgent.prepare` now reports canonical repository-backed counts and paths instead of reading from an in-memory `DataPipeline` store.
- `EvolutionLoop` now returns explicit blocked outcomes when current scores are unavailable, data preparation is not ready, or trainer validation/execution cannot proceed.
- `EvolutionLoop.run` no longer supports scoreless dry runs; a real `score_fn` is required.

**Review checklist**

- [x] Agents are thin and pipeline-driven
- [x] No infrastructure logic is embedded in agents
- [x] Placeholder execution paths are removed

**Review notes**

- `TrainerAgent` is now a thin orchestrator over `TrainingPipeline` and `EvaluationPipeline`; execution-provider access is injected and explicit rather than hidden in agent code.
- `DataAgent` no longer reports meaningless in-memory counts from `DataPipeline.count`; it inspects the canonical repository and returns honest readiness information.
- `EvolutionLoop` does not treat missing scores, missing execution providers, or invalid experiments as success paths. Those states become explicit `blocked` results with reasons.
- Agent-layer fake-success behavior has been removed: launched-without-evaluation and blocked-without-provider are represented explicitly, and only a real completed evaluation produces a `completed` step result.

**Test checklist**

- [x] Agents fail explicitly when required services are unavailable
- [x] Evolution loop uses real pipeline outputs

**Test record**

- Commands:
  - `pytest tests/test_agent.py tests/test_training.py tests/test_pipeline.py tests/test_foundation.py`
  - `python -m compileall forge tests`
  - `pytest`
- Result summary:
  - Added agent-thinning tests passed, covering blocked trainer execution without providers, launched-without-evaluation states, blocked evolution-loop outcomes, and completed loop outcomes only when a real evaluation report is available.
  - Full repository test suite passed: 180 tests.
  - Python compilation checks passed for the full `forge` package plus tests.
- Failures / gaps:
  - None remaining in the tested M5 path.
- Exit criteria:
  - Satisfied.

**Gate result**

- Review: pass
- Test: pass
- Result: milestone passed and was committed as `58b1cc1`.

**Commit record**

- Passing commit: `58b1cc1` (`refactor: thin agents over real pipelines`)

**Open issues / next step**

- Start M6 from CLI split and sidecar convergence.
- Keep blocked/launched/completed execution states explicit; do not reintroduce fake-success dry-run flows in agents.

## M6 — CLI + Sidecar Convergence

**Status:** `committed`

**Goal**

Finish the CLI split and isolate sidecars cleanly from the core architecture.

**Scope**

- CLI families: `data`, `train`, `eval`, `exp`, `remote`, `monitor`
- sidecars: `remote_ops`, `monitoring`, `domain_jobs`

**Out of scope**

- New product features beyond architecture completion

**Exit criteria**

- God modules are removed
- CLI responsibilities are separated by domain
- sidecars are explicit and independently auditable

**Implementation notes**

- Active slice started after M5 commit `58b1cc1`.
- Reorganized the root CLI around the six intended command families: `data`, `train`, `eval`, `exp`, `remote`, and `monitor`.
- Added `forge.remote_ops` as the explicit sidecar for compute, deployment, and remote-machine operations, with shared machine-selection helpers in `forge.remote_ops.service`.
- Added `forge.monitoring.cli` as the explicit monitoring sidecar CLI entrypoint for leaderboard and weakness analysis.
- Added `forge.domain_jobs.game` as the GAME-specific domain-jobs sidecar and reduced `forge.cli_game` to a compatibility wrapper.
- Added dedicated `eval` and `exp` command families for real evaluation execution and experiment lifecycle inspection.
- Reduced the root CLI to family registration only and removed direct top-level operational command implementations from `forge.cli`.
- Reduced `forge.cli_rental` and `forge.cli_game` to compatibility-oriented modules instead of primary navigation entrypoints.

**Review checklist**

- [x] CLI modules do not mix unrelated domains
- [x] Sidecars are isolated from the core layers
- [x] No cross-layer operational spillover remains in the core

**Review notes**

- The root CLI now acts as a composition root only; it registers family commands and no longer embeds leaderboard, compute, deployment, and rental implementations directly.
- Remote operational commands are explicitly grouped under the `remote` family and sidecar package instead of being mixed into the root CLI.
- Monitoring is now surfaced through the `monitor` family and monitoring sidecar package rather than a root-level `score` command.
- GAME-specific operational flows were moved behind the `domain_jobs` sidecar package, removing domain-specific remote logic from the root CLI path.
- Compatibility wrappers remain for `cli_rental` and `cli_game`, but the primary command navigation now matches the roadmap family structure and keeps operational spillover out of the core path.

**Test checklist**

- [x] CLI smoke tests cover command-family boundaries
- [x] Sidecar integration points are explicit and testable

**Test record**

- Commands:
  - `pytest tests/test_cli.py tests/test_agent.py tests/test_training.py tests/test_pipeline.py tests/test_foundation.py`
  - `python -m compileall forge tests`
  - `pytest`
- Result summary:
  - Added CLI smoke tests passed, verifying the root command families and sidecar subgroups (`remote`, `monitor`, `exp`) are exposed as intended.
  - Full repository test suite passed: 184 tests.
  - Python compilation checks passed for the full `forge` package plus tests.
- Failures / gaps:
  - None remaining in the tested M6 path.
- Exit criteria:
  - Satisfied.

**Gate result**

- Review: pass
- Test: pass
- Result: milestone passed and was committed as `b78c399`.

**Commit record**

- Passing commit: `b78c399` (`refactor: converge cli into sidecar families`)

**Open issues / next step**

- Refactor roadmap milestones M0 through M6 are now complete.
- Any further structural work should start from a roadmap update rather than continuing under the closed milestone plan.
