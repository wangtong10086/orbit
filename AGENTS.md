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
5. `docs/refactor/real-test-plan.md` when the task changes runtime behavior, CLI behavior, provider behavior, or end-to-end workflows
6. `docs/refactor/remediation-plan.md` when working from known real-test failures or reopening milestones after runtime validation

Do not recreate ad hoc roadmap or work-report files outside `docs/refactor/`. The current refactor document set is intentionally consolidated there.

## Refactor Mission

The refactor mission is to rebuild Affine Swarm as a two-plane system:

- a **control plane**
- an **execution plane**

Inside the control plane, the long-lived target shape remains:

- Layer 0: Foundation
- Layer 1: Pipelines
- Layer 2: Agents

Sidecars remain isolated operational or domain-specific modules that do not belong in the control-plane core or the execution plane.

The mission is not "move files until things look clean". The mission is to produce a system with explicit contracts, low coupling, real execution paths, and independent auditability.

## Non-Negotiable Architecture Rules

### 1. Preserve the control-plane trunk and execution-plane split

- The system-level split between control plane and execution plane must remain explicit.
- The control plane must remain centered on Foundation, Pipelines, and Agents.
- Do not flatten the whole system back into a monolith.
- Do not let sidecars or runtimes become a shadow layer that the control plane depends on implicitly.

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
- Infrastructure behavior belongs in execution runtimes or sidecars, not in agents or generic pipelines.
- If a module mixes policy, transport, and domain shaping, it is in the wrong place.

### 5. No placeholder abstractions pretending to be real

- Pipelines must represent real execution paths.
- Agents must not fabricate success from empty reports.
- Evaluation must not claim leaderboard semantics while implementing something different.
- If a component is still a stub, label it clearly and do not wire it in as if production-ready.

## Execution-Plane Policy

The execution plane is a first-class system module, not a sidecar.

Current execution-plane principles:

- bundle-first
- runtime-only platform logic
- control-later
- Docker-first development

Rules:

- `forge/execution/` owns execution contracts, bundles, runtimes, and worker-facing orchestration.
- `forge worker ...` is the primary execution-plane CLI.
- Task renderers may describe work, but they must not own Targon or SSH launch logic.
- Runtime backends may stage bundles and collect artifacts, but they must not redefine task semantics.

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

Within the execution plane, Targon has two valid runtime profiles and both must stay explicit:

- `bootstrap`
- `image`

Rules:

- Treat them as separate runtime profiles or backend modes.
- They may share a low-level control-plane client.
- Profile choice must be explicit in code and configuration.
- Do not add automatic mode fallback.
- Do not collapse them into one vague runtime path that branches invisibly at execution time.

Development and debugging exception:

- The `remote_ops` sidecar may expose explicit direct Targon API / CLI helpers for development and debugging.
- Those helpers are allowed for capacity checks, machine provisioning, workload inspection, and SDK-gap debugging.
- They must not become the default execution path for `train / eval / collect`.
- They must not leak Targon platform logic back into renderers, pipelines, agents, or generic data/training modules.

For real validation on Targon rental machines:

- do not default to the current `machines.json` inventory
- do not reuse a machine that is already running unrelated or production work
- provision or rent a **new isolated Targon rental machine** for the validation session
- only then register or reference it in the test commands

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

## Anti-Shortcut Rules

The following behaviors do **not** count as completing a refactor milestone:

- Wrapping an old module in a new namespace while keeping the old mixed-responsibility module on the active path.
- Renaming a God module without splitting its ownership.
- Keeping legacy orchestration entrypoints alive and calling them "compatibility" while CLI, tests, or active code still depend on them.
- Passing only smoke tests or `--help` tests while the actual ownership boundary is still violated.
- Leaving an old API exported from the active package surface after declaring the new path complete.
- Marking a milestone complete because the test suite is green, when the exit criteria are still visibly false in the codebase.

Practical rule:

- If the old path is still imported by active code, still registered in the primary CLI, or still validated as a primary path in tests, that old path is still active.
- An active old path means the milestone is not done.

## Compatibility Wrapper Policy

Compatibility wrappers are allowed only as short-lived migration aids.

Rules:

- A compatibility wrapper does not satisfy a milestone's completion criteria.
- A compatibility wrapper must not remain the primary path for CLI wiring, pipeline wiring, or tests.
- Tests must migrate away from compatibility wrappers before the milestone is closed.
- If a wrapper remains after a milestone is declared done, `progress.md` must explain exactly why it remains and what removes it.
- If that explanation no longer holds, reopen the milestone.

## Completion Evidence Policy

Every milestone closeout must include evidence in three categories:

### 1. Architecture evidence

Use static checks to prove the old path is no longer active.

Examples:

- `rg` for legacy imports, compatibility entrypoints, or duplicate orchestration symbols
- `wc -l` for modules that were supposed to be split
- package-surface checks to confirm old APIs are no longer exported

### 2. Behavior evidence

Use direct behavior tests, not just visibility tests.

Examples:

- command invocation tests for real CLI paths
- provider-selection tests for explicit runtime wiring
- configuration path resolution tests for real files, not just object construction

### 3. Regression evidence

Run the relevant targeted suite and the broader regression suite.

Minimum rule:

- targeted tests must prove the milestone boundary
- the broader suite must prove the refactor did not silently break unrelated paths

### 4. Real execution evidence

When a milestone changes runtime behavior, providers, remote operations, CLI execution paths, data flows, training flows, or evaluation flows, code tests alone are not enough.

You must execute the relevant parts of `docs/refactor/real-test-plan.md` and record:

- which checklist items were run
- which environments, machines, providers, and images were used
- log paths and artifact paths
- pass or fail outcome
- blockers or missing prerequisites

If the real-test plan is applicable and was not run, the milestone cannot be closed.

If the applicable real-test steps require Targon rental SSH or inference capacity, the validation session must provision or reserve a new isolated rental machine instead of treating `machines.json` as the default source of test hosts.

### 5. Self-test evidence for fixes

When fixing a bug that was discovered by a real test, audit, or live workflow:

- rerunning unit tests is not enough
- rerunning only nearby smoke tests is not enough

You must rerun:

1. the original failing command
2. at least one downstream command that depends on that fix

If the original failing command is still not rerun, the fix is incomplete.

If the downstream dependent command is not rerun, the fix is incomplete.

## CLI Refactor Rule

A CLI milestone is not complete just because the root command tree looks clean.

A CLI refactor is complete only when all three are true:

- primary command registration no longer points at legacy mixed-responsibility modules
- the remaining modules match ownership boundaries in practice, not just in names
- tests execute representative commands, not just `--help`

Moving `old_cli_module` behind `new_sidecar.cli` is still a shortcut if the old module remains the real implementation.

## Legacy Surface Rule

If a legacy class, function, or module remains exported from an active package surface, treat it as active until proven otherwise.

Rules:

- Old exports must be removed, quarantined behind clearly deprecated internal modules, or proven unused by active code and tests.
- Keeping both `new_pipeline` and `old_placeholder_pipeline` exported is not convergence.
- Keeping both `new_provider_path` and `old_runner_path` available is not convergence.

## Reopen Policy

Post-completion audits are allowed and expected for long refactors.

Rules:

- A milestone must be reopened if a later audit shows its exit criteria were not actually met.
- Historical passing commits remain as history, not as immunity from reopening.
- Once reopened, the live milestone status in `docs/refactor/progress.md` is authoritative.
- Future work must follow the reopened status, not the old commit message or old milestone narrative.

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

Test evidence is insufficient if it proves only command visibility or object construction while ownership boundaries remain unverified.

If the milestone changes an executable path, provider path, or user-facing operational workflow, the test gate must include both:

- code-level tests
- relevant real smoke tests or real end-to-end tests from `docs/refactor/real-test-plan.md`

Green unit tests without the required real-test evidence do not satisfy the test gate.

For known runtime regressions or remediation items, the test gate must also include the explicit self-test steps listed in `docs/refactor/remediation-plan.md`.

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
- Add or refine real-test runbooks when the refactor introduces new runtime behavior.

### Disallowed

- Adding a second active source of truth for roadmap or progress.
- Keeping both old and new execution paths indefinitely.
- Calling a legacy path "inactive" while it is still imported by active code, registered in CLI wiring, or covered as a primary path in tests.
- Declaring a milestone complete based on green smoke tests when ownership boundaries are still violated.
- Treating compatibility wrappers as the final architecture.
- Declaring runtime-facing work complete without running the applicable real-test checklist.
- Declaring a bugfix complete without rerunning the original failing command.
- Declaring a bugfix complete without rerunning at least one downstream dependent command.
- Treating mock-based integration tests as a substitute for remote/provider/training/evaluation real smoke tests.
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
- the policy for when real execution tests are mandatory
- the policy for when remediation self-tests are mandatory

Do not update this file for normal milestone progress; that belongs in `docs/refactor/progress.md`.
