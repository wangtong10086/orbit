# Documentation

This directory contains the active, user-facing documentation for the current
repository state.

Use this directory for:

- current architecture and concepts
- current CLI behavior
- current runtime and operations guidance
- current testing and validation guidance

Do not use this directory for:

- historical refactor process notes
- archived experiments or reports
- deep research notes that are not normative

## Read This First

Start here if you are new to the repository:

1. [../README.md](../README.md)
2. [architecture.md](architecture.md)
3. [cli.md](cli.md)
4. [operations.md](operations.md)
5. [testing.md](testing.md)
6. [test-runbook.md](test-runbook.md)

## Document Map

- [architecture.md](architecture.md)
  - current system structure
  - control plane / execution plane / sidecar boundaries
  - supported execution matrix
  - current limitations

- [cli.md](cli.md)
  - command families
  - recommended command paths
  - which command family owns which workflow

- [operations.md](operations.md)
  - environment variables
  - runtime assumptions
  - local vs Targon execution notes
  - machine and image prerequisites

- [testing.md](testing.md)
  - test layers
  - external dependency notes
  - validation reality

- [test-runbook.md](test-runbook.md)
  - practical verification commands
  - smoke-test sequences
  - doc-update validation checklist

## Historical and Secondary Material

- Refactor process records live in [refactor/README.md](refactor/README.md).
- Research and reference notes live in [../knowledge/README.md](../knowledge/README.md).
- Archived evaluation reports live in [../eval/README.md](../eval/README.md).

## Normative Scope

The normative documentation set for this repository is:

- `README.md`
- `docs/README.md`
- `docs/architecture.md`
- `docs/cli.md`
- `docs/operations.md`
- `docs/testing.md`
- `docs/test-runbook.md`

If other documents conflict with this set, prefer this set and current code.
