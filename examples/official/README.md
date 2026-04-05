# Official Remote Examples

This directory contains versioned example configs for official remote workflows.

Current official example:

- [`training/targon-qwen3-32b-full-sft.yaml`](training/targon-qwen3-32b-full-sft.yaml)
  - production-style remote training on Targon
  - Hugging Face dataset download
  - Hugging Face model repo creation
  - isolated Targon rental provisioning
  - control-plane submission through `orbit control launch train`

Copy and edit the example before use. The main documentation for this example
lives in [../../docs/official-examples.md](../../docs/official-examples.md).
