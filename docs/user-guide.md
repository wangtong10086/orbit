# User Guide

This guide explains how to use ORBIT at a workflow level. It is not the
quickest possible start, and it is not a full command reference. It is the
bridge between the project overview and the detailed reference docs.

## Recommended Reading Order

If you are new to the project, read in this order:

1. [../README.md](../README.md)
2. [getting-started.md](getting-started.md)
3. [this guide](user-guide.md)
4. [architecture.md](architecture.md)
5. [operations.md](operations.md)

## Default Mental Model

Think about ORBIT like this:

```text
  local machine                                 remote machine
  -------------                                 --------------
  orbit control                                 Targon rental
      |                                              |
      | submit through template                      | execute bundle
      v                                              v
  experiment + run record  <------------------  logs / artifacts
```

The normal operating model is:

- keep orchestration on your local machine
- use templates to choose how execution should happen
- execute the actual job on Targon
- inspect and collect the run from the control plane

## Choose The Right Workflow

### First remote run

Use:

- [getting-started.md](getting-started.md)
- template `targon-rental-host`
- a lightweight `submit collect` job

This is the primary documented and validated entrypoint.

### Production-style training

Use:

- [official-examples.md](official-examples.md)
- `python3 -m orbit control launch train --config ...`

Choose this when you want config-driven provisioning, launch, and optional
artifact publishing.

### Local debugging

Use:

- [debugging.md](debugging.md)
- [logging-and-artifacts.md](logging-and-artifacts.md)
- local `worker` flows

Choose this when you need to debug a bundle or runtime path before moving the
job to Targon.

## Core Concepts

### Experiment

An experiment is the control-plane record for what you are trying to run and
why. It stores metadata, run references, and task-related context.

### Execution template

A template describes the execution strategy:

- placement
- launch mode
- default image
- default execution behavior
- allowed overrides

In user terms, the template is how you say "run this kind of job in this kind
of environment" without wiring the runtime manually every time.

### Target

A target is the specific remote machine or rental you want to execute on.

For remote execution:

- targets are passed explicitly
- they are typically resolved through `machines.json`
- user-facing docs assume you will provide `--target` for Targon runs

### Bundle

A bundle is the execution handoff package. It contains:

- job metadata
- inputs
- entrypoint script
- artifact directory
- runtime state directory

The control side prepares or submits work; the execution side runs the bundle.

## Command Families

```text
  control  -> orchestrate and inspect runs
  worker   -> execute or debug bundles directly
  data     -> generate, ingest, and publish data
  remote   -> machine and provider operations
  monitor  -> monitoring and leaderboard tooling
```

Recommended default:

- use `control` for the main user workflow
- use `worker` when debugging a bundle directly
- use `remote` only for operational machine work

## What To Read Next

- [architecture.md](architecture.md): system boundaries and execution maturity
- [cli.md](cli.md): command ownership and usage paths
- [debugging.md](debugging.md): where to look first when a run fails
- [operations.md](operations.md): environment variables, targets, and runtime
  assumptions
- [official-examples.md](official-examples.md): official remote examples
