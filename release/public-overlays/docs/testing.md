# Testing Guide

This document describes the current testing reality for the public repository.
It covers what is actually validated in code and what still requires operator
runbooks outside the published source tree.

## Test Layers

The public repository currently relies on three practical layers:

- unit and integration tests under `tests/`
- CLI smoke checks
- maintainer-run real runtime validation sessions on Targon rentals

The public repository does not ship private run ledgers, experiment files, or
operator notebooks from those real validation sessions.

## What Is The Primary Validated Deployment Pattern?

The most important validated deployment pattern for this repository is:

- local control plane
- remote execution on Targon rentals
- preferred launch mode `host_process`
- primary documented template `targon-rental-host`

## Common CLI Checks

These help commands are expected to work:

```bash
python3 -m orbit --help
python3 -m orbit control --help
python3 -m orbit worker --help
python3 -m orbit data --help
python3 -m orbit remote --help
python3 -m orbit monitor --help
```

## Pytest Baseline

Current broad regression command:

```bash
pytest -q tests -q
```

Current status:

- passing in the maintainer workspace before public export

Additional targeted suites used during recent refactor closeout:

```bash
pytest -q tests/test_compute.py tests/test_control.py tests/test_data_cli.py tests/test_execution.py -q
pytest -q tests/test_execution.py tests/test_training.py tests/test_training_launch.py -q
```

Current status:

- passing in the maintainer workspace before public export

## What the Current Suite Proves

Today’s suite covers:

- current CLI command registration
- template-driven control paths
- generic execution contracts and worker flows
- data CLI and adjacent generation helpers
- compute and SSH/Targon transfer edge cases
- training-launch config validation for native `ms-swift` SFT and RLHF runs
- frozen task-source evaluation bundle wiring

## External Dependency Notes

Some workflows still rely on adjacent repositories or richer runtime images.

Examples:

- evaluation workflows may require `affinetes`
- LIVEWEB workflows may require `liveweb-arena`
- task-specific remote runs may require images with extra packages such as
  `pyspiel`

The core test suite is structured to remain runnable even when some of these
adjacent repositories are not installed locally.

## Real Validation

Code-level green tests are not the whole story for runtime-facing changes.

For runtime, provider, or remote-execution changes, also consult:

- [test-runbook.md](test-runbook.md)

Maintainers should keep separate private validation records for:

- exact remote commands run
- workload ids and machine ids
- image digests
- log paths and artifact paths
- pass/fail outcomes and blockers

Current public-repo validation status:

- the official training path has been real-validated on Targon from a clean
  public snapshot
- native `ms-swift` SFT and GKD configs are both supported through
  `orbit control launch train`

Key runtime-hardening fixes behind that validation:

- local teacher models and teacher adapters are staged into training bundles
  through explicit YAML placeholders
- `swift_passthrough` forwards unmodeled upstream `ms-swift` flags without
  overriding modeled fields
- experiment persistence uses file locking plus atomic replace so concurrent
  control workflows do not corrupt YAML state

## Documentation Rule

When updating testing docs, always record:

- exact commands run
- current result
- required external dependencies
- whether a failure is a code defect or an environment prerequisite
