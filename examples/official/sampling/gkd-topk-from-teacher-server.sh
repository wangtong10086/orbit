#!/usr/bin/env bash
set -euo pipefail

# Official offline-topk collection template for teacher-server GKD.
#
# Edit these values before use:
# - STUDENT_MODEL
# - TEACHER_MODEL_SERVER
# - INPUT_DATASET
# - OUTPUT_DIR
# - OUTPUT_FILE
# - GKD_LOGITS_TOPK
#
# Important:
# - use the same STUDENT_MODEL family here and in the later training config
# - the teacher server must support prompt_logprobs
# - the teacher server must support top_logprobs >= GKD_LOGITS_TOPK

STUDENT_MODEL="${STUDENT_MODEL:-Qwen/Qwen3-0.6B}"
TEACHER_MODEL_SERVER="${TEACHER_MODEL_SERVER:-http://<teacher-host>:8000}"
INPUT_DATASET="${INPUT_DATASET:-/abs/path/input.jsonl}"
OUTPUT_DIR="${OUTPUT_DIR:-/tmp/offline-gkd-output}"
OUTPUT_FILE="${OUTPUT_FILE:-offline_topk.jsonl}"
GKD_LOGITS_TOPK="${GKD_LOGITS_TOPK:-20}"

swift sample \
  --model "${STUDENT_MODEL}" \
  --sampler_type gkd_topk \
  --teacher_model_server "${TEACHER_MODEL_SERVER}" \
  --gkd_logits_topk "${GKD_LOGITS_TOPK}" \
  --dataset "${INPUT_DATASET}" \
  --output_dir "${OUTPUT_DIR}" \
  --output_file "${OUTPUT_FILE}"

echo
echo "offline-topk dataset written to:"
echo "  ${OUTPUT_DIR}/${OUTPUT_FILE}"
echo
echo "expected required fields:"
echo "  messages"
echo "  response_token_ids"
echo "  teacher_topk_indices"
echo "  teacher_topk_logprobs"
