#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:?usage: rental_sync_policy_code.sh <user@host> [remote_dir]}"
REMOTE_DIR="${2:-/root/affine-swarm}"
KEY_PATH="${AFFINE_RENTAL_KEY_PATH:-${HOME}/.ssh/affine_rental}"

TMP_TAR="$(mktemp /tmp/affine-game-sync.XXXXXX.tar.gz)"
trap 'rm -f "${TMP_TAR}"' EXIT

tar czf "${TMP_TAR}" \
  orbit \
  scripts \
  pyproject.toml \
  AGENTS.md \
  docs/refactor \
  docs/cli.md \
  README.md

ssh -i "${KEY_PATH}" -o StrictHostKeyChecking=no "${TARGET}" "mkdir -p '${REMOTE_DIR}'"
scp -i "${KEY_PATH}" -o StrictHostKeyChecking=no "${TMP_TAR}" "${TARGET}:/tmp/affine-game-sync.tar.gz"
ssh -i "${KEY_PATH}" -o StrictHostKeyChecking=no "${TARGET}" \
  "mkdir -p '${REMOTE_DIR}' && tar xzf /tmp/affine-game-sync.tar.gz -C '${REMOTE_DIR}' && rm -f /tmp/affine-game-sync.tar.gz"

echo "SYNCED ${TARGET} -> ${REMOTE_DIR}"
