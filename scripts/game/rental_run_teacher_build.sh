#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:?usage: rental_run_teacher_build.sh <user@host> <game>}"
GAME="${2:?usage: rental_run_teacher_build.sh <user@host> <game>}"
KEY_PATH="${AFFINE_RENTAL_KEY_PATH:-${HOME}/.ssh/affine_rental}"
REMOTE_DIR="${AFFINE_REMOTE_DIR:-/root/affine-swarm}"
REMOTE_PYTHON="${AFFINE_REMOTE_PYTHON:-${REMOTE_DIR}/.venv/bin/python}"
ITERATIONS="${AFFINE_GAME_POLICY_ITERATIONS:-0}"
LOG_PATH="${AFFINE_REMOTE_LOG_PATH:-/root/logs/${GAME}_teacher_build.log}"

ssh -i "${KEY_PATH}" -o StrictHostKeyChecking=no "${TARGET}" "\
  cd '${REMOTE_DIR}' && \
  export AFFINE_GAME_NAME='${GAME}' && \
  export AFFINE_GAME_BUILD_POLICY=1 && \
  export AFFINE_GAME_POLICY_ITERATIONS='${ITERATIONS}' && \
  PYTHONPATH='${REMOTE_DIR}' '${REMOTE_PYTHON}' scripts/game/targon_game_smoke.py \
  > '${LOG_PATH}' 2>&1"

echo "LOG ${LOG_PATH}"
