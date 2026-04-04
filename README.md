# Affine Swarm

Affine Swarm is a control-and-execution workspace for data generation, training,
evaluation, and remote runtime orchestration.

The repository is organized around three top-level concerns:

- `control plane`: experiment records, task orchestration, execution-template
  selection, status queries, and metadata capture
- `execution plane`: generic bundles, runtime contracts, execution backends,
  and the `forge worker` CLI
- `sidecars`: operational modules such as `remote_ops`, `monitoring`, and
  domain-specific helpers that do not belong in the core planes

This README is the user-facing entry point. It covers the current stable
surface. Historical refactor process documents live under `docs/refactor/`.

## Current Status

The current public execution model is:

- `local + host_process`
- `local + docker_image`
- `targon_rental + docker_image`

The current public orchestration model is template-driven:

- `forge control ...` orchestrates tasks through execution templates
- `forge worker ...` executes an already prepared generic bundle

Targon support currently covers rental machines only. If a task requires extra
runtime dependencies, choose an execution image that already contains them.

## Installation

```bash
cp .env.example .env
uv pip install -e .[all]
python -m forge --help
```

Optional extras currently group dependencies rather than strictly hiding
commands:

- `.[control]`: control/data/monitor dependencies
- `.[exec]`: worker/remote dependencies
- `.[all]`: full local setup

## Quickstart

Create an experiment and prepare a training bundle:

```bash
python -m forge control experiment create \
  --id v1 \
  --variable improve_game \
  --hypothesis "more data helps" \
  --train-config '{}' \
  --data-config '{}'

python -m forge control prepare train \
  v1 \
  tmp/game_train.jsonl \
  --bundle-dir tmp/bundle-train
```

Run the bundle locally:

```bash
python -m forge worker validate-bundle tmp/bundle-train
python -m forge worker run tmp/bundle-train --placement local --launch-mode host_process --foreground
```

Submit through the control plane with an execution template:

```bash
python -m forge control template list

python -m forge control submit train \
  v1 \
  tmp/game_train.jsonl \
  --template targon-rental-docker \
  --target <rental-machine> \
  --image wangtong123/affine-forge:latest
```

## Command Families

```bash
python -m forge --help
python -m forge control --help
python -m forge worker --help
python -m forge data --help
python -m forge remote --help
python -m forge monitor --help
```

Current command families:

- `control`: experiment lifecycle, template registry, prepare/submit/run flows
- `worker`: bundle validation, execution, logs, artifact collection, terminate
- `data`: generation, ingestion, canonical sync, publishing, and dataset ops
- `remote`: low-level Targon and machine debugging sidecar
- `monitor`: monitoring and leaderboard sidecar

## Documentation

The active documentation entry point is [docs/README.md](docs/README.md).

Main documents:

- [docs/architecture.md](docs/architecture.md): current architecture and
  concepts
- [docs/cli.md](docs/cli.md): command surface and recommended usage paths
- [docs/operations.md](docs/operations.md): environment, runtime, and Targon
  operational notes
- [docs/testing.md](docs/testing.md): test layers and validation reality
- [docs/test-runbook.md](docs/test-runbook.md): copy-paste validation commands

Historical refactor records:

- [docs/refactor/README.md](docs/refactor/README.md)

Reference and archive material:

- [knowledge/README.md](knowledge/README.md)
- [eval/README.md](eval/README.md)

## Current Limitations

- Experiment persistence is currently file-based YAML storage, not a
  transactional state store.
- Some domain CLIs still prepare bundles directly before calling the worker,
  instead of routing every path through `forge control`.
- Targon rental validation is covered, but task-specific dependency stacks are
  still image-dependent. For example, a task may need an image with `pyspiel`
  or other non-default packages.

## Historical Documents

The following files are retained for history only and are not current sources
of truth:

- [PLAYBOOK.md](PLAYBOOK.md)
- [CLAUDE.md](CLAUDE.md)
- documents under `knowledge/` and `eval/` unless explicitly marked otherwise

When these files conflict with `README.md`, `docs/`, or current code, treat the
latter as authoritative.
