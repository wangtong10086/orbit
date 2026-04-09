#!/usr/bin/env bash
# Optional helper for recipes that explicitly require flash-attn.
# The default ORBIT native GKD path does not call this script.
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
    echo "[flash-attn] uv is required" >&2
    exit 1
fi

log() {
    echo "[flash-attn] $*"
}

install_build_deps() {
    uv pip install --no-cache "ninja>=1.11" packaging wheel setuptools >/dev/null
}

try_prebuilt() {
    log "trying prebuilt wheel"
    uv pip install --no-cache --only-binary=:all: flash-attn
}

build_from_source() {
    log "prebuilt wheel unavailable; building from source"
    install_build_deps
    export MAX_JOBS="${MAX_JOBS:-$(nproc)}"
    export FLASH_ATTENTION_FORCE_BUILD=TRUE
    uv pip install --no-cache --no-build-isolation flash-attn
}

verify_import() {
    python3 - <<'PY'
import flash_attn
print(getattr(flash_attn, "__version__", "unknown"))
PY
}

if try_prebuilt; then
    version="$(verify_import)"
    log "installed prebuilt flash-attn ${version}"
    exit 0
fi

build_from_source
version="$(verify_import)"
log "installed source-built flash-attn ${version}"
