![ORBIT logo](docs/assets/logo.png)

# ORBIT

Orchestrated Research, Benchmarking, and Iterative Training

ORBIT is a control-and-execution workspace for running training, evaluation,
and collection jobs from a local control plane onto Targon rental machines.

Its main use case is straightforward: operate jobs locally, execute them on
Targon, and collect logs and artifacts through explicit templates instead of
ad-hoc remote orchestration.

## Overview

ORBIT is organized around four concerns:

- `control plane`: experiment records, task orchestration, template selection,
  and run inspection
- `execution plane`: generic bundles, placement backends, launch modes, and
  artifact collection
- `task plugins`: training, evaluation, and collection request shaping
- `sidecars`: operational helpers such as remote ops and monitoring

The default documented workflow is:

- local `control`
- remote `targon_rental`
- launch mode `host_process`
- template `targon-rental-host`

## Features

- Targon-first remote execution from a local control plane
- explicit execution templates instead of hidden runtime branching
- bundle-based execution with runtime audit logs
- separate control-plane and execution-plane responsibilities
- official config-driven remote training example
- `uv`-based setup as the default environment workflow

## Documentation

Start here:

- [Getting Started](docs/getting-started.md): first remote run on Targon
- [User Guide](docs/user-guide.md): how to think about workflows, targets, and
  command families

Reference:

- [Documentation Hub](docs/README.md)
- [Architecture](docs/architecture.md)
- [CLI Guide](docs/cli.md)
- [Operations Guide](docs/operations.md)
- [Official Remote Examples](docs/official-examples.md)
- [Testing Guide](docs/testing.md)
- [Test Runbook](docs/test-runbook.md)

## Project Status

Supported execution matrix:

- `local + host_process`
- `local + docker_image`
- `targon_rental + host_process`
- `targon_rental + docker_image`

Primary documented and validated path:

- local `control` -> `targon_rental + host_process`

Other paths remain available but are documented as secondary.

## Community

- [LICENSE](LICENSE)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- [SECURITY.md](SECURITY.md)

## Historical Material

- [docs/refactor/README.md](docs/refactor/README.md): refactor governance archive
- [docs/research/README.md](docs/research/README.md): research and historical
  background material
