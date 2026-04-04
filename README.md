# Affine Swarm

Affine Swarm is a control-and-execution workspace for data generation, training,
evaluation, and remote runtime orchestration.

The repository is organized around three top-level concerns:

- `control plane`: experiment records, task orchestration, execution-template
  selection, status queries, and metadata capture
- `execution plane`: generic bundles, runtime contracts, execution backends,
  and the `forge worker` CLI
- `task plugins`: task-specific request parsing, bundle building, and result
  summarization for training, evaluation, and collection
- `sidecars`: operational modules such as `remote_ops`, `monitoring`, and
  domain-specific helpers that do not belong in the core planes

This README is the user-facing entry point. It covers the current stable
surface. Historical refactor process documents live under `docs/refactor/`.

## Current Status

The current public execution model is:

- `local + host_process`
- `local + docker_image`
- `targon_rental + host_process`
- `targon_rental + docker_image`

The current public orchestration model is template-driven:

- `forge control ...` orchestrates tasks through execution templates
- `forge worker ...` executes an already prepared generic bundle
- the generic kernel lives under `forge/core/*`
- built-in task plugins live under `forge/tasks/*`

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
python -m forge worker collect tmp/bundle-train
```

After collection, execution-plane audit logs are available inside the bundle:

- `runtime/runtime.log`: runtime actions such as staging, launch, status probes,
  artifact collection, and termination
- `artifacts/stdout.log`
- `artifacts/stderr.log`

Submit through the control plane with an execution template:

```bash
python -m forge control template list

python -m forge control submit train \
  v1 \
  tmp/game_train.jsonl \
  --template targon-rental-host \
  --target <rental-machine>
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
- [docs/official-examples.md](docs/official-examples.md): supported one-command
  example configs
- [docs/testing.md](docs/testing.md): test layers and validation reality
- [docs/test-runbook.md](docs/test-runbook.md): copy-paste validation commands

Historical refactor records:

- [docs/refactor/README.md](docs/refactor/README.md)

## Official Training Example

The supported one-command training example is:

```bash
python -m forge control launch train \
  --config examples/official/training/targon-qwen3-32b-full-sft.yaml
```

Before running it:

- put `HF_TOKEN`, `TARGON_API_KEY`, `TARGON_PROJECT_ID`, and
  `TARGON_SSH_KEY_UID` into `.env`
- edit the config's experiment id, Hugging Face model repo, and Targon rental
  names
- set `publish.private: true` for a private Hugging Face repo or `false` for a
  public one

Validated behavior:

- the launcher can create the target Hugging Face model repo
- a real training run can complete on Targon
- the final training artifacts can be uploaded automatically to either a
  private or a public Hugging Face repo

See [docs/official-examples.md](docs/official-examples.md) for the full flow.

## Current Limitations

- Experiment persistence is currently file-based YAML storage, not a
  transactional state store.
- Some domain CLIs still expose convenience workflows that orchestrate task
  submission outside the main `forge control` command family, even though they
  now route through the same core control kernel.
- Built-in task plugins are in-repo modules, not separately packaged external
  plugins.
- Targon rental validation is covered, but task-specific dependency stacks are
  still image-dependent. For example, a task may need an image with `pyspiel`
  or other non-default packages.
- Runtime logs are append-only bundle-local files. They improve execution
  auditability, but they are not yet mirrored into a separate central log
  store beyond the existing audit event stream under `logs/audit/`.

## Historical Documents

The following files are retained for history only and are not current sources
of truth:

- [PLAYBOOK.md](PLAYBOOK.md)
- [CLAUDE.md](CLAUDE.md)

When these files conflict with `README.md`, `docs/`, or current code, treat the
latter as authoritative.
