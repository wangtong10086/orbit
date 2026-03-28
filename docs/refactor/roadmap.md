# Refactor Roadmap

**Status:** Active

## Refactor Goal

Rebuild Affine Swarm around a clean three-layer architecture with explicit contracts, composition-first design, and independently auditable sidecar capabilities.

The target end state is:

- Layer 0 contains stable, reusable foundations with explicit contracts.
- Layer 1 contains business pipelines built only by composing Layer 0 capabilities.
- Layer 2 contains thin agents that make decisions and orchestrate pipelines.
- Features that do not fit the three-layer core cleanly are extracted into focused sidecars instead of distorting the main architecture.

## Current Problem Summary

The current codebase has several structural issues that this refactor must remove:

- Claimed three-layer boundaries do not match the real dependency graph.
- Environment discovery depends on import side effects and global registries.
- Some agent and pipeline abstractions are placeholders that look real but do not execute real work.
- Training execution is duplicated across parallel codepaths.
- Large CLI modules mix unrelated concerns such as remote operations, data shaping, evaluation orchestration, and environment-specific logic.
- Some scoring and evaluation semantics diverge from the documented leaderboard rules.
- Several operational features are real requirements, but they do not fit the three-layer core and should become sidecars.

## Target Architecture

### Layer 0 — Foundation

Layer 0 owns stable primitives and contracts. These modules must remain low-coupling and explicitly wired.

- `EnvironmentCatalog`
- `EnvironmentDefinition`
- `ConversationPacker`
- `TrainingSpec`
- `ExecutionProvider`
- `ArtifactStore`
- `EvaluationRunner`
- `ScoringPolicy`
- `CanonicalRepository`

Rules:

- No import side effect registration.
- No hidden global mutable registries.
- Prefer `Protocol` plus composed collaborators over inheritance-heavy hierarchies.
- Environment-specific formatting belongs in packers and definitions, not in CLI modules.

### Layer 1 — Pipelines

Layer 1 owns business workflows built by composing Layer 0 contracts.

- `DataIngestPipeline`
- `DatasetBuildPipeline`
- `TrainingPipeline`
- `EvaluationPipeline`
- `ExperimentService`

Rules:

- Pipelines do orchestration only.
- Pipelines may depend on Layer 0 contracts and repositories.
- Pipelines must not own transport-specific or provider-specific policy beyond explicit provider selection.

### Layer 2 — Agents

Layer 2 owns decision-making and orchestration of pipelines.

- `StrategistAgent`
- `TrainerAgent`
- `DataAgent`
- `EvolutionLoop`

Rules:

- Agents do not implement infrastructure logic.
- Agents do not fake execution success with placeholder reports.
- Agents only call real pipelines and explicit services.

### Sidecars

The following capabilities are explicitly modeled as sidecars rather than forced into the three-layer core:

- `remote_ops`
- `monitoring`
- `domain_jobs`

Rules:

- Each sidecar must be independently testable and auditable.
- Sidecars may integrate with the core through explicit interfaces only.
- Sidecars must not reintroduce cross-layer shortcuts.

## Key Contracts

The refactor is organized around these long-lived contracts:

- `EnvironmentCatalog`
- `TrainingSpec`
- `ExecutionProvider`
- `ArtifactStore`
- `ScoringPolicy`
- `CanonicalRepository`

These contracts are the stability anchors for the refactor. Changes to them require roadmap updates and explicit milestone review.

Current contract modules:

- `forge.foundation.environment_catalog`: `EnvironmentCatalog`, `EnvironmentDefinition`
- `forge.foundation.contracts`: `TrainingSpec`, `EvaluationSpec`, `ExecutionProvider`, `ArtifactStore`, `CanonicalRepository`, `ConversationPacker`, `EvaluationRunner`
- `forge.foundation.scoring`: `ScoringPolicy.strict_geo_mean`

Strict scoring semantics for the refactor:

- `ScoringPolicy.strict_geo_mean` is the only valid core geometric-mean implementation.
- It operates directly on the provided per-environment scores with no epsilon smoothing.
- If any included environment score is `0`, the strict geometric mean is `0`.
- Empty score sets return `0`.
- Negative scores are invalid input and must be rejected.

## Targon Modeling

Targon remains a first-class execution target, but its two operational modes are modeled separately:

- `TargonBootstrapProvider`
- `TargonImageProvider`

They share a common low-level control-plane client, but they are treated as distinct execution providers at the architecture level.

Provider responsibilities:

- `TargonBootstrapProvider`: start from the official Targon base image, bootstrap/install the runtime environment, then execute training or evaluation workloads.
- `TargonImageProvider`: start directly from a prebuilt image and inject runtime configuration and artifacts only.

Rules:

- Provider selection must be explicit.
- No automatic fallback between Targon modes.
- Shared control-plane code must not leak mode-specific policy upward.

## Milestone Roadmap

### M0 — Governance Skeleton

- Goal: create the `docs/refactor/` documentation system and define the mandatory gates for all following milestones.
- Depends on: none.
- Done when:
  - `docs/refactor/README.md`, `docs/refactor/roadmap.md`, and `docs/refactor/progress.md` exist.
  - These files are referenced as the only active source of truth for this refactor.
  - The gate workflow is documented and reusable.

### M1 — Foundation Contracts + Catalog

- Goal: establish explicit contracts and replace import side effect environment registration with `EnvironmentCatalog`.
- Depends on: M0.
- Done when:
  - foundation contracts are defined and documented.
  - environment discovery is explicit.
  - strict scoring policy is documented as the only valid scoring rule.

### M2 — Data Usable Path

- Goal: make canonical ingest and dataset build a real composed path with packers pushed down.
- Depends on: M1.
- Done when:
  - `CanonicalRepository` exists.
  - `ConversationPacker` owns model-specific conversation packing.
  - ingest and dataset build are pipeline-driven.

### M3 — Training Usable Path

- Goal: unify training execution and remove duplicated runner and executor paths.
- Depends on: M1.
- Done when:
  - `TrainingPipeline` is the only orchestration entrypoint.
  - `SshExecutionProvider`, `TargonBootstrapProvider`, and `TargonImageProvider` exist.
  - old dual execution paths are removed.

### M4 — Evaluation Usable Path

- Goal: make evaluation a real execution path with strict scoring semantics.
- Depends on: M1 and M3.
- Done when:
  - `EvaluationPipeline` and `EvaluationRunner` are real execution components.
  - `ScoringPolicy.strict_geo_mean` is the only scoring implementation used by evaluation reports.

### M5 — Agent Thinning

- Goal: make agents true orchestration and decision layers instead of mixed execution layers.
- Depends on: M2, M3, and M4.
- Done when:
  - agents call real pipelines only.
  - placeholder execution logic is removed.
  - `EvolutionLoop` no longer accepts fake-success paths.

### M6 — CLI + Sidecar Convergence

- Goal: split God modules, finish CLI reorganization, and isolate sidecars cleanly.
- Depends on: M2, M3, M4, and M5.
- Done when:
  - CLI is organized around `data`, `train`, `eval`, `exp`, `remote`, and `monitor`.
  - sidecars are isolated and the core no longer contains operational spillover logic.

## Gate Rules

### Review Gate

Every milestone must end with a complete architecture review. The review must explicitly confirm:

- layer boundaries still match the three-layer core plus sidecar model.
- no new cross-layer shortcuts or hidden global state were introduced.
- no duplicated execution path or split source of truth remains.
- auditability is preserved for both the core and each affected sidecar.
- obsolete compatibility layers or placeholder abstractions were removed when replaced.

Review results must be written into `progress.md`.

### Test Gate

Every milestone must define and execute a milestone-specific test set.

The test record must include:

- exact commands run
- summary of results
- failures or gaps
- whether exit criteria were satisfied

If tests do not pass, the milestone remains active and must continue iterating within the same milestone.

### Commit Gate

Only milestones that pass both review and test gates may be committed as complete.

Rules:

- each milestone must have at least one explicit passing commit.
- the final passing commit hash must be recorded in `progress.md`.
- milestones are not marked `committed` before review and test gates pass.

## Non-Goals

The current phase does not aim to:

- keep the old CLI layout for compatibility
- preserve placeholder abstractions purely for continuity
- introduce machine-readable duplicate status files
- solve unrelated product or model-quality issues during architecture work
- execute code refactors in the same step as governance setup

## Roadmap Change Policy

This file should only change when one of the following happens:

- milestone order or scope changes
- architecture boundary definitions change
- a core contract changes
- governance or gate rules change

Routine milestone execution details belong in `progress.md`, not here.

## Execution Charter

Refactor execution is additionally governed by the repository-level `AGENTS.md`.

Policy:

- `AGENTS.md` defines anti-drift execution rules.
- `roadmap.md` remains the authority for architecture direction, contracts, milestones, and governance intent.
- `progress.md` remains the authority for live milestone state.
