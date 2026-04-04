# Architecture

This document describes the current repository architecture. It covers the
stable concepts and boundaries that are visible in the codebase today. It does
not replay the historical refactor narrative in detail.

## System Model

Affine Swarm is organized as a two-plane system with explicit task plugins and
sidecars:

- `control plane`
- `execution plane`
- `task plugins`
- `sidecars`

## Control Plane

Primary locations:

- `forge/core/control`
- `forge/core/experiments`
- `forge/core/templates`
- `forge/control` compatibility facade
- `forge/cli_control.py`

Current responsibilities:

- store experiment records
- resolve task plugins and execution templates
- resolve `template + overrides -> execution request`
- submit runs, query status, read logs, collect artifacts
- persist run metadata and audit records

Current public model:

- control paths are template-driven
- submit paths are based on `template_id + overrides`
- task-specific specs live above the execution core

## Execution Plane

Primary locations:

- `forge/core/execution`
- `forge/execution` compatibility facade
- `forge/cli_worker.py`

Current responsibilities:

- define generic bundle layout
- define generic execution contracts
- own placement and launch-mode backends
- execute bundles
- collect logs, artifacts, and terminal state

Execution-plane core is task-agnostic. It does not treat training, evaluation,
or collection as special runtime types.

## Task Plugins

Primary locations:

- `forge/tasks/training`
- `forge/tasks/evaluation`
- `forge/tasks/collection`

Current responsibilities:

- parse and validate task-specific requests
- build generic execution bundles
- summarize task-specific outputs after artifact collection

The core control kernel depends on explicit plugin registration. It does not
import task implementations directly.

## Sidecars

Current sidecars:

- `forge/remote_ops`
- `forge/monitoring`
- `forge/domain_jobs`

Sidecars are intentionally separate from the two planes. They may support
operational workflows, debugging, or domain-specific tooling, but they should
not silently become the main architecture path.

## Core Concepts

### Execution Template

An execution template is the control-plane registration unit.

It describes execution strategy rather than a specific machine. In practice it
captures:

- placement
- launch mode
- default image
- default resource request
- default execution behavior such as detach mode
- allowed overrides

### Placement

Current public placements:

- `local`
- `targon_rental`

### Launch Mode

Current public launch modes:

- `host_process`
- `docker_image`

### Bundle

A bundle is the execution-plane handoff artifact. It contains:

- `job.json`
- `inputs/`
- `scripts/entrypoint.sh`
- `artifacts/`
- `runtime/`

Task plugins are responsible for generating bundles. The execution plane is
responsible for running them. Remote bundle staging excludes local runtime
state and stale artifact payloads so a remote run starts from a clean bundle
snapshot.

## Supported Execution Matrix

Current public execution paths:

- `local + host_process`
- `local + docker_image`
- `targon_rental + docker_image`
- `targon_rental + host_process`

## Targon Boundary

Current Targon support is intentionally narrow:

- rental only
- no serverless abstraction in the main execution model
- no app abstraction in the main execution model

Targon platform details belong below the control plane, typically in execution
backends or the `remote_ops` sidecar.

For GPU tasks on rentals, the preferred path is now:

- start the rental from the target execution image
- expose SSH on the rental
- execute bundles directly on the rental host process

This avoids relying on Docker-in-Docker GPU semantics inside a rental host.

## Current Boundary Rules

- The control plane chooses templates and records metadata; it does not own
  Docker or SSH execution details.
- The execution plane owns generic runtime behavior; it does not redefine task
  semantics.
- Task plugins live above the execution core.
- `forge/core/*` does not import `forge/tasks/*`; plugin registration happens
  in explicit composition roots.
- Sidecars may help with provisioning or debugging, but they are not the
  default train/eval/collect execution path.

## Current Limitations

- Experiment persistence is file-based YAML storage with merge-save semantics,
  not a transactional state store.
- Some domain-oriented CLI paths still expose convenience orchestration outside
  the main `forge control` command family, even when they use the same core
  control kernel underneath.
- Task runtime dependencies remain image-dependent. A task may require a custom
  image even when the execution path itself is valid.

## Related Documents

- [cli.md](cli.md)
- [operations.md](operations.md)
- [testing.md](testing.md)
- [refactor/README.md](refactor/README.md)
