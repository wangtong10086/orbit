# Refactor Governance Docs

This directory is the source of truth for the current long-running refactor of Affine Swarm.

The active refactor goal is now a **control plane + execution plane** system:

- the control plane will keep the long-lived three-layer core
- the execution plane will own bundle rendering and real task execution

## Core Principles

- Keep the system-level split between control plane and execution plane explicit.
- Keep the control-plane core as Foundation, Pipelines, and Agents.
- Prefer composition, explicit contracts, and explicit wiring over inheritance and hidden global state.
- Move poor fits for the control-plane core into focused sidecars or the execution plane instead of forcing them into the main abstraction.
- Treat architecture boundaries and auditability as first-class constraints.

## Document Index

- [`roadmap.md`](roadmap.md): long-term refactor route, target architecture, contracts, milestones, and governance rules.
- [`progress.md`](progress.md): milestone-by-milestone execution log, gate outcomes, review notes, and commit records.
- [`real-test-plan.md`](real-test-plan.md): executable runbook for real smoke tests and real end-to-end validation beyond the repository test suite.
- [`remediation-plan.md`](remediation-plan.md): repair checklist and mandatory self-test commands derived from real-test failures.
- [`../../AGENTS.md`](../../AGENTS.md): execution charter for future refactor tasks; use it to stay aligned, but not as a replacement for roadmap or progress tracking.

## Active Policy

Use only the documents in `docs/refactor/` plus [`../../AGENTS.md`](../../AGENTS.md) for current refactor execution.

Older ad hoc refactor notes and partial work-report files have been removed from the active documentation set to avoid split source of truth problems.
