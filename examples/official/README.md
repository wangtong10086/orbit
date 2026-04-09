# Official Remote Examples

This directory contains versioned example configs for official remote workflows.

Current official examples:

- [`training/targon-qwen3-32b-full-sft.yaml`](training/targon-qwen3-32b-full-sft.yaml)
  - production-style remote training on Targon
  - Hugging Face dataset download
  - Hugging Face model repo creation
  - isolated Targon rental provisioning
  - control-plane submission through `orbit control launch train`
- [`training/targon-qwen3-0.6b-gkd-offline-topk.yaml`](training/targon-qwen3-0.6b-gkd-offline-topk.yaml)
  - offline-topk GKD training from a prepared dataset
- [`training/targon-qwen3-0.6b-gkd-offline-topk-push-to-hf.yaml`](training/targon-qwen3-0.6b-gkd-offline-topk-push-to-hf.yaml)
  - end-to-end offline-topk GKD training with Hugging Face upload enabled
- [`sampling/gkd-topk-from-teacher-server.sh`](sampling/gkd-topk-from-teacher-server.sh)
  - teacher-server collection template for offline top-k dataset generation
- [`sampling/gkd-topk-from-teacher-server-to-hf.sh`](sampling/gkd-topk-from-teacher-server-to-hf.sh)
  - teacher-server collection template that also uploads sampled data to a Hugging Face dataset repo

Copy and edit the example before use. The main documentation for this example
lives in [../../docs/official-examples.md](../../docs/official-examples.md).
