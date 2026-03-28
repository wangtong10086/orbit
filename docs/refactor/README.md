# Refactor Governance Docs

This directory is the source of truth for the current long-running refactor of Affine Swarm.

The goal of this refactor is to rebuild the system around a stable three-layer core, use composition over inheritance, and move hard-to-abstract operational features into small sidecar modules that remain independently auditable.

## Core Principles

- Keep the main architecture as three layers: Foundation, Pipelines, Agents.
- Prefer composition, explicit contracts, and explicit wiring over inheritance and hidden global state.
- Move poor fits for the three-layer core into focused sidecars instead of forcing them into the main abstraction.
- Treat architecture boundaries and auditability as first-class constraints.

## Document Index

- [`roadmap.md`](roadmap.md): long-term refactor route, target architecture, contracts, milestones, and governance rules.
- [`progress.md`](progress.md): milestone-by-milestone execution log, gate outcomes, review notes, and commit records.
- [`../../AGENTS.md`](../../AGENTS.md): execution charter for future refactor tasks; use it to stay aligned, but not as a replacement for roadmap or progress tracking.

## Historical Docs

The following files are retained as historical reference only and do not describe the current refactor state:

- [`../refactoring-plan.md`](../refactoring-plan.md)
- [`../work-report.md`](../work-report.md)

When the current refactor is in progress, do not use those files as execution guidance. Use only the documents in `docs/refactor/`.
