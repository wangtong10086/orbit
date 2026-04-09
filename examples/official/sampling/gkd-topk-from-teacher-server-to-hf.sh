#!/usr/bin/env bash
set -euo pipefail

# Official durable offline-topk collection template.
#
# This wrapper:
# 1. runs `swift sample --sampler_type gkd_topk`
# 2. validates the sampled JSONL
# 3. uploads the result to a Hugging Face dataset repo
#
# Edit these values before use.

STUDENT_MODEL="${STUDENT_MODEL:-Qwen/Qwen3-0.6B}"
TEACHER_MODEL_SERVER="${TEACHER_MODEL_SERVER:-http://<teacher-host>:8000}"
INPUT_DATASET="${INPUT_DATASET:-/abs/path/input.jsonl}"
OUTPUT_DIR="${OUTPUT_DIR:-/tmp/offline-gkd-output}"
OUTPUT_FILE="${OUTPUT_FILE:-offline_topk.jsonl}"
GKD_LOGITS_TOPK="${GKD_LOGITS_TOPK:-20}"
HF_REPO="${HF_REPO:-your-hf-username/your-offline-topk-dataset}"
HF_PATH="${HF_PATH:-offline_topk/offline_topk.jsonl}"

python3 scripts/sample_offline_topk_and_upload.py \
  --use-hf \
  --model "${STUDENT_MODEL}" \
  --teacher-model-server "${TEACHER_MODEL_SERVER}" \
  --gkd-logits-topk "${GKD_LOGITS_TOPK}" \
  --dataset "${INPUT_DATASET}" \
  --output-dir "${OUTPUT_DIR}" \
  --output-file "${OUTPUT_FILE}" \
  --hf-repo "${HF_REPO}" \
  --hf-path "${HF_PATH}" \
  --create-repo
