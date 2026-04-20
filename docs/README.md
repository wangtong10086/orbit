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
- [offline-gkd.md](offline-gkd.md): offline-topk GKD design and runtime flow
- [offline-gkd-quickstart.md](offline-gkd-quickstart.md): end-to-end offline-topk
  collection, training, and Hugging Face publish guide
- [operations.md](operations.md): environment variables, targets, and runtime
  expectations

## Reference

- [architecture.md](architecture.md): architecture and execution maturity
- [cli.md](cli.md): command-family reference
- [debugging.md](debugging.md): debugging entrypoint and log-surface map
- [logging-and-artifacts.md](logging-and-artifacts.md): artifact/log tutorial
- [nvml-gpu-audit.md](nvml-gpu-audit.md): GPU memory audit tutorial
- [pydantic-validation.md](pydantic-validation.md): contract/schema validation guide
- [swe-synthesis-pipeline.md](swe-synthesis-pipeline.md): standalone guide to
  the active SWE synth pipeline
- [swe-synthesis-pipeline-zh.md](swe-synthesis-pipeline-zh.md): 中文算法说明版
  SWE synth pipeline 文档
- [testing.md](testing.md): testing reality
- [test-runbook.md](test-runbook.md): maintainer validation commands

## Research & Compatibility

- [research/README.md](research/README.md): design notes and historical context
- [architecture-zh.md](architecture-zh.md): compatibility entry for older links

## Documentation Rules

- User-facing docs are English-first.
- The default documented path is local `control` plus Targon execution.
- The repository root README is intentionally short and index-oriented.
- Detailed setup, quick start, workflow guidance, and architecture live under
  `docs/`.
