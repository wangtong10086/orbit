# Testing Guide

This document describes the current testing reality. It covers what is actually
validated today, not an idealized future state.

## Test Layers

The repository currently relies on three practical layers:

- unit and integration tests under `tests/`
- CLI smoke checks
- real runtime validation records under `logs/real-tests/`

## What Is The Primary Validated Deployment Pattern?

The most important validated deployment pattern for this repository is:

- local control plane
- remote execution on Targon rentals
- preferred launch mode `host_process`
- primary documented template `targon-rental-host`

This matters because the user-facing docs prioritize validated Targon-backed
workflows over local-only debugging paths.

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

- passing

Additional targeted suites used during recent refactor closeout:

```bash
pytest -q tests/test_compute.py tests/test_control.py tests/test_data_cli.py tests/test_execution.py -q
```

Current status:

- passing

Additional targeted suites for the staged VG-SOPD workflow:

```bash
pytest -q tests/test_compute.py tests/test_vg_sopd.py tests/test_training_launch.py -q
```

Current status:

- passing

## What the Current Suite Proves

Today’s suite covers:

- current CLI command registration
- template-driven control paths
- generic execution contracts and worker flows
- data CLI and adjacent generation helpers
- compute and SSH/Targon transfer edge cases
- staged VG-SOPD task specs, compiler outputs, teacher routing, and multi-run
  experiment recording

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

## Documentation Rule

When updating testing docs, always record:

- exact commands run
- current result
- required external dependencies
- whether a failure is a code defect or an environment prerequisite
