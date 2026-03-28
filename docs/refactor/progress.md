# Refactor Progress

This file is the execution log for the active refactor. It records milestone status, review outcomes, test outcomes, and commit gates.

## Overview

| Milestone | Status | Primary deliverable | Last reviewed commit | Next gate |
|---|---|---|---|---|
| M0 | committed | Refactor governance docs in `docs/refactor/` | `ee3f4fd` | Start M1 |
| M1 | committed | Foundation contracts and `EnvironmentCatalog` | `3bd074a` | Start M2 |
| M2 | planned | Data usable path and packer ownership | N/A | Start milestone |
| M3 | planned | Unified training path and execution providers | N/A | Start milestone |
| M4 | planned | Real evaluation path and strict scoring | N/A | Start milestone |
| M5 | planned | Thin agents over real pipelines | N/A | Start milestone |
| M6 | planned | CLI reorganization and sidecar convergence | N/A | Start milestone |

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

**Status:** `planned`

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

- Pending milestone start.

**Review checklist**

- [ ] Data path is repository-driven instead of in-memory placeholder state
- [ ] Packers own environment/model-specific shaping logic
- [ ] CLI modules do not own conversation normalization logic

**Test checklist**

- [ ] Ingest path covers dedup against existing canonical data
- [ ] Dataset build covers LIVEWEB/NAVWORLD packing

**Gate result**

- Not started

**Commit record**

- N/A

**Open issues / next step**

- Start after M1 is committed.

## M3 — Training Usable Path

**Status:** `planned`

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

- Pending milestone start.

**Review checklist**

- [ ] No duplicated training orchestration remains
- [ ] Provider choice is explicit
- [ ] Shared Targon control-plane code stays low-level

**Test checklist**

- [ ] Training specs can target SSH and both Targon providers
- [ ] Provider launch payloads and status contracts are consistent

**Gate result**

- Not started

**Commit record**

- N/A

**Open issues / next step**

- Start after M2 is committed.

## M4 — Evaluation Usable Path

**Status:** `planned`

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

- Pending milestone start.

**Review checklist**

- [ ] Evaluation is not a placeholder abstraction
- [ ] Scoring policy is shared across report generation and strategy logic
- [ ] Documentation and implementation semantics match

**Test checklist**

- [ ] Evaluation path returns real results
- [ ] Strict geo mean tests cover empty, single, mixed, and zero-score cases

**Gate result**

- Not started

**Commit record**

- N/A

**Open issues / next step**

- Start after M3 is committed.

## M5 — Agent Thinning

**Status:** `planned`

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

- Pending milestone start.

**Review checklist**

- [ ] Agents are thin and pipeline-driven
- [ ] No infrastructure logic is embedded in agents
- [ ] Placeholder execution paths are removed

**Test checklist**

- [ ] Agents fail explicitly when required services are unavailable
- [ ] Evolution loop uses real pipeline outputs

**Gate result**

- Not started

**Commit record**

- N/A

**Open issues / next step**

- Start after M4 is committed.

## M6 — CLI + Sidecar Convergence

**Status:** `planned`

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

- Pending milestone start.

**Review checklist**

- [ ] CLI modules do not mix unrelated domains
- [ ] Sidecars are isolated from the core layers
- [ ] No cross-layer operational spillover remains in the core

**Test checklist**

- [ ] CLI smoke tests cover command-family boundaries
- [ ] Sidecar integration points are explicit and testable

**Gate result**

- Not started

**Commit record**

- N/A

**Open issues / next step**

- Start after M5 is committed.
