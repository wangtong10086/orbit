#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <snapshot-dir>" >&2
  exit 2
fi

SNAPSHOT_DIR="$1"
UV_BIN="${UV_BIN:-uv}"
PYTHON_VERSION="${PYTHON_VERSION:-3.11}"
TMP_LYCHEE="${TMP_LYCHEE:-/tmp/orbit-public-lychee}"

cd "$SNAPSHOT_DIR"

test -f "orbit/core/experiments/__init__.py"
test -f "scripts/vllm_teacher_qwen3_235b_tp8.sh"

if find . \( -name '.env' -o -name '*.pem' -o -name '*.key' -o -name 'id_*' \) -print | grep -q .; then
  echo "sensitive file found in public snapshot" >&2
  exit 1
fi

for forbidden in experiments logs artifacts tmp; do
  if [ -e "$forbidden" ]; then
    echo "forbidden path leaked into public snapshot: $forbidden" >&2
    exit 1
  fi
done

if rg -n \
  --hidden \
  --glob '!**/.git/**' \
  '(ghp_[A-Za-z0-9]{36}|gho_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]+|sk-or-v1-[A-Za-z0-9]+|cpk_[A-Za-z0-9._-]{20,}|hf_[A-Za-z0-9]{20,}|BEGIN OPENSSH PRIVATE KEY|BEGIN RSA PRIVATE KEY)' \
  .; then
  echo "secret-like token or private key material found in public snapshot" >&2
  exit 1
fi

"$UV_BIN" venv --python "$PYTHON_VERSION"
"$UV_BIN" pip install --python .venv/bin/python -e ".[control]"
"$UV_BIN" pip install --python .venv/bin/python pytest build

.venv/bin/python -m compileall -q orbit/ scripts/
.venv/bin/python -m orbit --help
.venv/bin/python -m orbit control --help
.venv/bin/python -m orbit worker --help
.venv/bin/python -m pytest -q tests/test_cli.py tests/test_control.py tests/test_execution.py tests/test_compute.py -q
.venv/bin/python -m build

rm -rf "$TMP_LYCHEE"
mkdir -p "$TMP_LYCHEE"
curl -sfLo "$TMP_LYCHEE/lychee.tar.gz" \
  https://github.com/lycheeverse/lychee/releases/download/lychee-v0.23.0/lychee-x86_64-unknown-linux-gnu.tar.gz
tar -xzf "$TMP_LYCHEE/lychee.tar.gz" -C "$TMP_LYCHEE"
"$TMP_LYCHEE/lychee" --verbose --no-progress README.md docs
