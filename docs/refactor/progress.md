# Refactor Progress

This file is the execution log for the active refactor. It records milestone status, review outcomes, test outcomes, and commit gates.

## Overview

| Milestone | Status | Primary deliverable | Last reviewed commit | Next gate |
|---|---|---|---|---|
| M0 | in_progress | Refactor governance docs in `docs/refactor/` | N/A | Review gate |
| M1 | planned | Foundation contracts and `EnvironmentCatalog` | N/A | Start milestone |
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

**Status:** `in_progress`

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

- [ ] `docs/refactor/README.md` is navigation-only and does not duplicate roadmap/progress detail
- [ ] `docs/refactor/roadmap.md` contains long-lived architecture and governance decisions only
- [ ] `docs/refactor/progress.md` contains milestone execution state only
- [ ] Source-of-truth language is explicit and unambiguous
- [ ] Gate rules are usable for every future milestone

**Test checklist**

- [ ] Confirm all three files exist under `docs/refactor/`
- [ ] Confirm links in `README.md` resolve correctly
- [ ] Confirm milestone table includes M0 through M6
- [ ] Confirm allowed status values are documented
- [ ] Confirm `AGENTS.md` exists at the repository root and points future work back to `docs/refactor/`

**Gate result**

- Review: pending
- Test: pending
- Result: milestone remains `in_progress` until both gates pass

**Commit record**

- Pending. No passing milestone commit recorded yet.

**Open issues / next step**

- Read the new files end-to-end and perform the first M0 review.
- Run simple file-existence and link-consistency checks.
- If review and checks pass, update M0 to `passed` and record the passing commit when created.

## M1 — Foundation Contracts + Catalog

**Status:** `planned`

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

- Pending milestone start.

**Review checklist**

- [ ] No hidden global registration remains in the active architecture path
- [ ] Contracts are explicit and composition-friendly
- [ ] Scoring semantics match documented leaderboard rules

**Test checklist**

- [ ] Catalog construction works without side-effect imports
- [ ] Scoring tests cover zero-score behavior

**Gate result**

- Not started

**Commit record**

- N/A

**Open issues / next step**

- Start after M0 is committed.

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
