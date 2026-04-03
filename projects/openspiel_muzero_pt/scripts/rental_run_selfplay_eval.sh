#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:?usage: rental_run_selfplay_eval.sh <user@host> <game> <teacher|best>}"
GAME="${2:?usage: rental_run_selfplay_eval.sh <user@host> <game> <teacher|best>}"
OPPONENT="${3:?usage: rental_run_selfplay_eval.sh <user@host> <game> <teacher|best>}"
KEY_PATH="${AFFINE_RENTAL_KEY_PATH:-${HOME}/.ssh/affine_rental}"
REMOTE_DIR="${AFFINE_REMOTE_DIR:-/root/affine-swarm}"
REMOTE_PYTHON="${AFFINE_REMOTE_PYTHON:-${REMOTE_DIR}/.venv/bin/python}"
LOG_PATH="${AFFINE_REMOTE_LOG_PATH:-/root/logs/${GAME}_selfplay_eval_${OPPONENT}.log}"
QUICK_GAMES="${AFFINE_GAME_SELFPLAY_QUICK_GAMES:-50}"
TEACHER_GAMES="${AFFINE_GAME_SELFPLAY_TEACHER_GAMES:-200}"
HF_TOKEN_VALUE="${HF_TOKEN:-}"

ssh -i "${KEY_PATH}" -o StrictHostKeyChecking=no "${TARGET}" "\
  cd '${REMOTE_DIR}' && \
  export AFFINE_GAME_NAME='${GAME}' && \
  export AFFINE_GAME_SELFPLAY_EVAL_OPPONENT='${OPPONENT}' && \
  export AFFINE_GAME_SELFPLAY_QUICK_GAMES='${QUICK_GAMES}' && \
  export AFFINE_GAME_SELFPLAY_TEACHER_GAMES='${TEACHER_GAMES}' && \
  export HF_TOKEN='${HF_TOKEN_VALUE}' && \
  PYTHONPATH='${REMOTE_DIR}' '${REMOTE_PYTHON}' scripts/game/targon_game_smoke.py \
  > '${LOG_PATH}' 2>&1"

echo "LOG ${LOG_PATH}"
