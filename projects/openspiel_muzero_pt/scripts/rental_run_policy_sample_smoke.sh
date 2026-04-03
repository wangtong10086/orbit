#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:?usage: rental_run_policy_sample_smoke.sh <user@host> <game>}"
GAME="${2:?usage: rental_run_policy_sample_smoke.sh <user@host> <game>}"
KEY_PATH="${AFFINE_RENTAL_KEY_PATH:-${HOME}/.ssh/affine_rental}"
REMOTE_DIR="${AFFINE_REMOTE_DIR:-/root/affine-swarm}"
REMOTE_PYTHON="${AFFINE_REMOTE_PYTHON:-${REMOTE_DIR}/.venv/bin/python}"
SAMPLE_COUNT="${AFFINE_GAME_SAMPLE_COUNT:-2}"
ATTEMPT_MULTIPLIER="${AFFINE_GAME_ATTEMPT_MULTIPLIER:-4}"
LOG_PATH="${AFFINE_REMOTE_LOG_PATH:-/root/logs/${GAME}_policy_sample.log}"

ssh -i "${KEY_PATH}" -o StrictHostKeyChecking=no "${TARGET}" "\
  cd '${REMOTE_DIR}' && \
  export AFFINE_GAME_NAME='${GAME}' && \
  export AFFINE_GAME_GENERATOR_SOURCE=policy_model && \
  export AFFINE_GAME_SAMPLE_COUNT='${SAMPLE_COUNT}' && \
  export AFFINE_GAME_ATTEMPT_MULTIPLIER='${ATTEMPT_MULTIPLIER}' && \
  PYTHONPATH='${REMOTE_DIR}' '${REMOTE_PYTHON}' scripts/game/targon_game_smoke.py \
  > '${LOG_PATH}' 2>&1"

echo "LOG ${LOG_PATH}"
