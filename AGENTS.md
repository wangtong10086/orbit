# Refactor Agents Charter

This file is the execution charter for all future refactor work in this repository.

It exists to keep long-running refactor tasks aligned, prevent local optimizations from drifting away from the target architecture, and make sure every engineer or agent follows the same rules.

## Authority and Scope

- `docs/refactor/` remains the only active source of truth for refactor state.
- `AGENTS.md` defines how refactor work must be executed.
- `AGENTS.md` does not replace roadmap, milestone, or progress tracking.
- If `AGENTS.md` conflicts with `docs/refactor/roadmap.md` on architecture or milestone intent, update the roadmap first, then align this file.

## Required Reading Before Any Refactor Task

Before starting any non-trivial refactor task, read in order:

1. `AGENTS.md`
2. `docs/refactor/README.md`
3. `docs/refactor/roadmap.md`
4. `docs/refactor/progress.md`

Do not rely on `docs/refactoring-plan.md` or `docs/work-report.md` for current refactor execution decisions. They are historical only.

## Refactor Mission

The refactor mission is to rebuild Affine Swarm around a clean three-layer core while keeping hard-to-abstract operational features in small sidecars.

Target shape:

- Layer 0: Foundation
- Layer 1: Pipelines
- Layer 2: Agents
- Sidecars: isolated operational or domain-specific modules that do not belong in the core

The mission is not "move files until things look clean". The mission is to produce a system with explicit contracts, low coupling, real execution paths, and independent auditability.

## Non-Negotiable Architecture Rules

### 1. Preserve the three-layer main trunk

- The main system must remain centered on Foundation, Pipelines, and Agents.
- Do not flatten the architecture back into a monolith.
- Do not let sidecars become a shadow fourth layer that core flows silently depend on.

### 2. Prefer composition over inheritance

- Build behavior from explicit collaborators.
- Prefer `Protocol` plus composition over base-class trees.
- Avoid "framework-like" inheritance hierarchies for environments, pipelines, or agents unless there is a concrete repeated lifecycle that cannot be composed cleanly.

### 3. No hidden global state

- No import side effect registration in active architecture paths.
- No global mutable registries unless they are wrapped in explicit composition roots and treated as local wiring only.
- No runtime behavior that depends on importing modules in a specific order.

### 4. Keep boundaries audit-friendly

- Every core capability should be inspectable through an explicit interface.
- Environment shaping rules belong in environment definitions or packers, not in CLI glue.
- Infrastructure behavior belongs in providers or sidecars, not in agents or generic pipelines.
- If a module mixes policy, transport, and domain shaping, it is in the wrong place.

### 5. No placeholder abstractions pretending to be real

- Pipelines must represent real execution paths.
- Agents must not fabricate success from empty reports.
- Evaluation must not claim leaderboard semantics while implementing something different.
- If a component is still a stub, label it clearly and do not wire it in as if production-ready.

## Sidecar Policy

Some capabilities are required but do not fit the three-layer core cleanly. Those should become sidecars rather than distorting the main architecture.

Current intended sidecars:

- `remote_ops`
- `monitoring`
- `domain_jobs`

Rules for sidecars:

- Keep the sidecar small and focused.
- Connect it to the core through explicit contracts only.
- Do not let sidecars own core domain rules that belong in Foundation or Pipelines.
- Do not park messy logic in sidecars just to avoid proper design work.

## Targon Policy

Targon has two valid operational modes and both must stay explicit:

- `TargonBootstrapProvider`
- `TargonImageProvider`

Rules:

- Treat them as separate execution providers.
- They may share a low-level control-plane client.
- Provider choice must be explicit in code and configuration.
- Do not add automatic mode fallback.
- Do not collapse them into one vague provider that branches invisibly at runtime.

## Source-of-Truth Policy

Use each document for one purpose only:

- `docs/refactor/README.md`: entry and navigation
- `docs/refactor/roadmap.md`: long-lived route, contracts, architecture boundaries, milestone definitions
- `docs/refactor/progress.md`: live milestone status, review outcomes, test outcomes, commit records
- `AGENTS.md`: execution charter and anti-drift rules

Do not create duplicate status documents, duplicate roadmap files, or ad hoc milestone notes outside this structure unless the roadmap is updated first.

## Milestone Discipline

All work must map to the active milestone in `docs/refactor/progress.md`.

Rules:

- Do not work on a later milestone while the current one has not passed its gate.
- If a task spans multiple milestones, split it and finish the current milestone part first.
- If new required scope appears, update `progress.md` and, if needed, `roadmap.md` before continuing.
- Do not mark a milestone complete in conversation only; the record must live in `progress.md`.

## Mandatory Gates

Every milestone must pass all three gates:

### Review Gate

Check at minimum:

- layer boundaries still match the target architecture
- no new cross-layer coupling was introduced
- no duplicated execution path or split source of truth was introduced
- sidecars remain independently auditable
- stale compatibility layers and fake abstractions are being removed rather than accumulated

### Test Gate

Record at minimum:

- exact commands run
- summary of results
- failures, gaps, or skipped coverage
- whether milestone exit criteria are satisfied

### Commit Gate

- Only milestone work that passes review and test gates should be committed as a milestone pass.
- Record the passing commit hash in `docs/refactor/progress.md`.
- If the milestone fails review or testing, keep iterating within the same milestone.

## Allowed and Disallowed Refactor Moves

### Allowed

- Introduce explicit contracts and composition roots.
- Split large modules by responsibility.
- Delete dead compatibility code after replacement is verified.
- Move environment-specific formatting into packers or environment definitions.
- Move operational spillover into focused sidecars.
- Rename modules when it improves boundary clarity.

### Disallowed

- Adding a second active source of truth for roadmap or progress.
- Keeping both old and new execution paths indefinitely.
- Solving architecture problems with more flags, more branching, or more hidden conventions.
- Moving domain logic into CLI modules.
- Reintroducing import-triggered discovery as a convenience shortcut.
- Marking work "done" without updating the milestone record.

## Definition of Good Refactor Work

A refactor change is good only if it improves at least one of these without regressing the others:

- clearer ownership
- lower coupling
- more explicit contracts
- more honest execution paths
- easier review and auditing
- easier milestone verification

Cosmetic movement without architectural improvement does not count as success.

## When to Update This File

Update `AGENTS.md` only when one of these changes:

- the anti-drift rules for refactor execution
- the governance model around milestones or gates
- the allowed/disallowed execution patterns for agents or engineers
- the relationship between `AGENTS.md` and `docs/refactor/`

Do not update this file for normal milestone progress; that belongs in `docs/refactor/progress.md`.
