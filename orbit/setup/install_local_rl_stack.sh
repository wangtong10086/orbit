#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

ORBIT_TORCH_VERSION="${ORBIT_TORCH_VERSION:-2.10.0}"
ORBIT_TRANSFORMERS_VERSION="${ORBIT_TRANSFORMERS_VERSION:-4.57.6}"
ORBIT_SWIFT_VERSION="${ORBIT_SWIFT_VERSION:-4.0.4}"
ORBIT_VLLM_VERSION="${ORBIT_VLLM_VERSION:-0.19.0}"

if ! command -v uv >/dev/null 2>&1; then
    echo "[ORBIT] uv is required before install_local_rl_stack.sh" >&2
    exit 1
fi

if [ ! -f "${PROJECT_ROOT}/pyproject.toml" ]; then
    echo "[ORBIT] project root does not look valid: ${PROJECT_ROOT}" >&2
    exit 1
fi

FORK_ROOT="${PROJECT_ROOT}/packages/affine_ms_swift/vendor/ms_swift_fork"
RL_RUNTIME_ROOT="${PROJECT_ROOT}/packages/rl_runtime"
BACKEND_ROOT="${PROJECT_ROOT}/packages/affine_ms_swift"
ENV_MEMORYGYM_ROOT="${PROJECT_ROOT}/packages/env_memorygym"
ENV_AFFINETES_ROOT="${PROJECT_ROOT}/packages/env_affinetes"
MEMORYGYM_ROOT="${PROJECT_ROOT}/repos/MemoryGym"

if [ ! -f "${FORK_ROOT}/pyproject.toml" ]; then
    echo "[ORBIT] local ms-swift fork is missing at ${FORK_ROOT}" >&2
    exit 1
fi

if [ ! -f "${MEMORYGYM_ROOT}/pyproject.toml" ]; then
    echo "[ORBIT] local MemoryGym checkout is missing at ${MEMORYGYM_ROOT}" >&2
    exit 1
fi

export AFFINE_MS_SWIFT_FORK_ROOT="${FORK_ROOT}"
export AFFINE_MEMORYGYM_ROOT="${MEMORYGYM_ROOT}"

echo "[ORBIT] installing validated runtime core..."
uv pip install --no-cache \
    "torch==${ORBIT_TORCH_VERSION}" \
    "transformers==${ORBIT_TRANSFORMERS_VERSION}" \
    "vllm==${ORBIT_VLLM_VERSION}"

echo "[ORBIT] removing upstream ms-swift distributions if present..."
uv pip uninstall -y ms-swift affine-ms-swift-fork >/dev/null 2>&1 || true

echo "[ORBIT] installing orbit[exec] without upstream ms-swift..."
uv pip install --no-cache "${PROJECT_ROOT}[exec]"

echo "[ORBIT] installing local affine RL packages..."
uv pip install --no-cache \
    "${RL_RUNTIME_ROOT}" \
    "${BACKEND_ROOT}" \
    "${ENV_MEMORYGYM_ROOT}" \
    "${ENV_AFFINETES_ROOT}"

echo "[ORBIT] installing local MemoryGym package..."
uv pip install --no-cache "${MEMORYGYM_ROOT}"

echo "[ORBIT] installing local affine ms-swift fork wheel..."
uv pip install --no-cache "${FORK_ROOT}"

pip uninstall torchao -y >/dev/null 2>&1 || true

python3 - <<'PY'
import importlib.metadata as im
import json
import os
from pathlib import Path

import swift

print(f"swift.import.version={getattr(swift, '__version__', 'unknown')}")
print(f"swift.import.path={Path(swift.__file__).resolve()}")
try:
    print(f"affine-ms-swift-fork.dist.version={im.version('affine-ms-swift-fork')}")
except im.PackageNotFoundError:
    print("affine-ms-swift-fork.dist.version=missing")
try:
    import pynvml
    print(f"pynvml.import.version={getattr(pynvml, '__version__', 'unknown')}")
except Exception as exc:
    print(f"pynvml.import.error={exc}")
manifest_path = Path(os.environ["AFFINE_MS_SWIFT_FORK_ROOT"]) / "FORK_MANIFEST.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
print(f"affine-ms-swift-fork.manifest.upstream={manifest.get('upstream_version', '')}")
print(f"affine-ms-swift-fork.manifest.fork={manifest.get('fork_version', '')}")
PY
