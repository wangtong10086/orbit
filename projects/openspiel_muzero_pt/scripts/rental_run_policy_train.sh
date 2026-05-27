#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:?usage: rental_run_policy_train.sh <user@host> <game>}"
GAME="${2:?usage: rental_run_policy_train.sh <user@host> <game>}"
KEY_PATH="${AFFINE_RENTAL_KEY_PATH:-${HOME}/.ssh/affine_rental}"
REMOTE_DIR="${AFFINE_REMOTE_DIR:-/root/personal-project}"
REMOTE_PYTHON="${AFFINE_REMOTE_PYTHON:-${REMOTE_DIR}/.venv/bin/python}"
LOG_PATH="${AFFINE_REMOTE_LOG_PATH:-/root/logs/${GAME}_policy_train.log}"
POLICY_ITERATIONS="${AFFINE_GAME_POLICY_ITERATIONS:-0}"
EXPERT_SAMPLES="${AFFINE_GAME_EXPERT_SAMPLES:-0}"
POLICY_EPOCHS="${AFFINE_GAME_POLICY_EPOCHS:-0}"
POLICY_BATCH_SIZE="${AFFINE_GAME_POLICY_BATCH_SIZE:-0}"
POLICY_HIDDEN_DIM="${AFFINE_GAME_POLICY_HIDDEN_DIM:-0}"
POLICY_DEVICE="${AFFINE_GAME_POLICY_DEVICE:-}"

ssh -i "${KEY_PATH}" -o StrictHostKeyChecking=no "${TARGET}" "\
  cd '${REMOTE_DIR}' && \
  export AFFINE_GAME_NAME='${GAME}' && \
  export AFFINE_GAME_BUILD_POLICY=1 && \
  export AFFINE_GAME_BUILD_EXPERT_DATASET=1 && \
  export AFFINE_GAME_TRAIN_POLICY_MODEL=1 && \
  export AFFINE_GAME_POLICY_ITERATIONS='${POLICY_ITERATIONS}' && \
  export AFFINE_GAME_EXPERT_SAMPLES='${EXPERT_SAMPLES}' && \
  export AFFINE_GAME_POLICY_EPOCHS='${POLICY_EPOCHS}' && \
  export AFFINE_GAME_POLICY_BATCH_SIZE='${POLICY_BATCH_SIZE}' && \
  export AFFINE_GAME_POLICY_HIDDEN_DIM='${POLICY_HIDDEN_DIM}' && \
  export AFFINE_GAME_POLICY_DEVICE='${POLICY_DEVICE}' && \
  PYTHONPATH='${REMOTE_DIR}' '${REMOTE_PYTHON}' scripts/game/targon_game_smoke.py \
  > '${LOG_PATH}' 2>&1"

echo "LOG ${LOG_PATH}"
