#!/usr/bin/env bash
set -euo pipefail

APT_PACKAGES=(
  python3
  python3-pip
  python3-venv
  rsync
  git
  curl
  screen
  openssh-sftp-server
  build-essential
  cmake
)

TORCH_INDEX_URL="${AFFINE_TORCH_INDEX_URL:-https://download.pytorch.org/whl/cu128}"
PYTHON_BIN="${AFFINE_PYTHON_BIN:-python3}"
VENV_DIR="${AFFINE_REMOTE_VENV:-/root/personal-project/.venv}"

APT_PREFIX=()
if command -v sudo >/dev/null 2>&1; then
  APT_PREFIX=(sudo)
fi

"${APT_PREFIX[@]}" apt-get update
"${APT_PREFIX[@]}" env DEBIAN_FRONTEND=noninteractive apt-get install -y "${APT_PACKAGES[@]}"

"${PYTHON_BIN}" -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/python" -m pip install --upgrade pip
"${VENV_DIR}/bin/python" -m pip install \
  --extra-index-url "${TORCH_INDEX_URL}" \
  torch
"${VENV_DIR}/bin/python" -m pip install \
  numpy \
  open_spiel \
  click \
  huggingface_hub \
  pydantic \
  pydantic-settings

mkdir -p /root/personal-project /root/logs /root/artifacts
echo "READY ${VENV_DIR}"
