#!/usr/bin/env bash
set -euo pipefail

# Production-style offline-topk collection:
# 1. prepare once
# 2. collect per bucket with high teacher concurrency
# 3. flush parts incrementally
# 4. upload parts to a HF dataset repo

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT"

export HF_TOKEN="${HF_TOKEN:?set HF_TOKEN}"
export HF_DATASET_REPO="${HF_DATASET_REPO:-waston10086/orbit-offline-topk-canonical-qwen3-235b-fp8}"

python3 scripts/collect_offline_topk_dataset.py \
  --dataset /tmp/orbit-gkd-qwen3-32b-msswift-20260408T151500Z/canonical_ms_swift.jsonl \
  --output-dir /tmp/offline-topk-canonical-prod \
  --model Qwen/Qwen3-32B \
  --teacher-model-server http://127.0.0.1:13000 \
  --gkd-logits-topk 20 \
  --max-length 32768 \
  --bucket-boundaries 8192,16384,32768 \
  --hf-repo "$HF_DATASET_REPO" \
  --hf-prefix offline_topk/canonical \
  --create-repo \
  --request-batch-size 8 \
  --b8-inflight 64 \
  --b16-inflight 32 \
  --b32-inflight 8 \
  --flush-rows 512 \
  --flush-seconds 900
