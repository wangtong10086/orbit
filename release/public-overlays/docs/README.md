# Documentation

This directory contains the user-facing documentation for ORBIT.

The docs are intentionally organized around the primary documented workflow:
operate the control plane locally and execute jobs on Targon rentals.

## Start Here

- [../README.md](../README.md): repository overview
- [getting-started.md](getting-started.md): first remote run on Targon
- [user-guide.md](user-guide.md): workflow-level guide to experiments,
  templates, targets, and command families

## Remote Training & Evaluation

- [official-examples.md](official-examples.md): official remote examples
- [operations.md](operations.md): environment variables, targets, and runtime
  expectations

## Reference

- [architecture.md](architecture.md): architecture and execution maturity
- [cli.md](cli.md): command-family reference
- [testing.md](testing.md): testing reality
- [test-runbook.md](test-runbook.md): maintainer validation commands

## Documentation Rules

- User-facing docs are English-first.
- The default documented path is local `control` plus Targon execution.
- The repository root README is intentionally short and index-oriented.
- Detailed setup, quick start, workflow guidance, and architecture live under
  `docs/`.
