#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:?usage: rental_run_long_job.sh <user@host> [job-name]}"
JOB_NAME="${2:-${AFFINE_GAME_LONGRUN_JOB_NAME:-game-longrun}}"
SESSION_NAME="${AFFINE_GAME_LONGRUN_SESSION:-${JOB_NAME}}"
KEY_PATH="${AFFINE_RENTAL_KEY_PATH:-${HOME}/.ssh/affine_rental}"
REMOTE_DIR="${AFFINE_REMOTE_DIR:-/root/affine-swarm}"
REMOTE_PYTHON="${AFFINE_REMOTE_PYTHON:-${REMOTE_DIR}/.venv/bin/python}"
LOG_PATH="${AFFINE_REMOTE_LOG_PATH:-/root/logs/${JOB_NAME}.log}"
ROOT_DIR="${AFFINE_GAME_LONGRUN_ROOT:-${REMOTE_DIR}/artifacts/game_longrun/${JOB_NAME}}"

POLICY_REPO="${AFFINE_GAME_POLICY_REPO:-}"
HF_TOKEN_VALUE="${HF_TOKEN:-}"

ssh -i "${KEY_PATH}" -o StrictHostKeyChecking=no "${TARGET}" "\
  mkdir -p '${REMOTE_DIR}' /root/logs '${ROOT_DIR}' && \
  screen -S '${SESSION_NAME}' -X quit 2>/dev/null || true && \
  cd '${REMOTE_DIR}' && \
  export PYTHONPATH='${REMOTE_DIR}' && \
  export PYTHONUNBUFFERED=1 && \
  export AFFINE_GAME_LONGRUN_JOB_NAME='${JOB_NAME}' && \
  export AFFINE_GAME_LONGRUN_ROOT='${ROOT_DIR}' && \
  export AFFINE_GAME_POLICY_REPO='${POLICY_REPO}' && \
  export HF_TOKEN='${HF_TOKEN_VALUE}' && \
  screen -dmS '${SESSION_NAME}' bash -lc \"'${REMOTE_PYTHON}' -u scripts/game/game_longrun_job.py > '${LOG_PATH}' 2>&1\""

echo "SESSION ${SESSION_NAME}"
echo "LOG ${LOG_PATH}"
echo "ROOT ${ROOT_DIR}"
