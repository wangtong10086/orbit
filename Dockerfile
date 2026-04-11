# ORBIT — Execution Runtime Image
#
# Build:
#   docker build \
#     --network host \
#     --build-arg HTTP_PROXY=$http_proxy \
#     --build-arg HTTPS_PROXY=$https_proxy \
#     --build-arg NO_PROXY=$no_proxy \
#     -t wangtong123/orbit:latest .
#
# Push:
#   docker push wangtong123/orbit:latest
#
# This image packages the execution plane only. It intentionally excludes
# editor, shell-theme, and other interactive development tooling so GitHub
# Actions can build it within standard runner disk limits.

FROM nvidia/cuda:12.8.1-devel-ubuntu22.04

LABEL maintainer="orbit"
LABEL description="ORBIT execution plane — native ms-swift training runtime"

ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ARG http_proxy
ARG https_proxy
ARG no_proxy
ARG MAX_JOBS=0

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV HTTP_PROXY=${HTTP_PROXY:-${http_proxy}}
ENV HTTPS_PROXY=${HTTPS_PROXY:-${https_proxy}}
ENV NO_PROXY=${NO_PROXY:-${no_proxy}}
ENV http_proxy=${http_proxy:-${HTTP_PROXY}}
ENV https_proxy=${https_proxy:-${HTTPS_PROXY}}
ENV no_proxy=${no_proxy:-${NO_PROXY}}
ENV MAX_JOBS=${MAX_JOBS}
ENV ORBIT_TORCH_VERSION=2.10.0
ENV ORBIT_TRANSFORMERS_VERSION=4.57.6
ENV ORBIT_VLLM_VERSION=0.19.0
ENV AFFINE_MS_SWIFT_FORK_ROOT=/opt/orbit-src/packages/affine_ms_swift/vendor/ms_swift_fork
ENV AFFINE_MEMORYGYM_ROOT=/opt/orbit-src/repos/MemoryGym

RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    build-essential git curl wget unzip \
    zsh tmux screen htop jq \
    openssh-server openssh-client rsync \
    libnuma1 libnuma-dev \
    ninja-build \
    software-properties-common \
    ca-certificates gnupg \
    && rm -rf /var/lib/apt/lists/*

# ── Python tooling ──────────────────────────────────────────────────
ENV UV_INSTALL_DIR=/usr/local/bin
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
RUN uv python install 3.11

ENV VIRTUAL_ENV=/opt/orbit-venv
RUN uv venv $VIRTUAL_ENV --python 3.11
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV UV_CACHE_DIR=/tmp/uv-cache

# ── Force HuggingFace downloads (not ModelScope) ───────────────────
ENV USE_MODELSCOPE=False
ENV USE_HF=1
ENV HF_HOME="/data/.cache/huggingface"
ENV TRANSFORMERS_CACHE="/data/.cache/huggingface/hub"
# Prefer a less fragmentation-prone CUDA allocator for large local full-param runs.
ENV PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"

# ── Project source + execution-plane dependencies ──────────────────
COPY README.md /opt/orbit-src/README.md
COPY pyproject.toml /opt/orbit-src/pyproject.toml
COPY orbit/ /opt/orbit-src/orbit/
COPY packages/ /opt/orbit-src/packages/
COPY repos/MemoryGym/ /opt/orbit-src/repos/MemoryGym/
COPY scripts/ /opt/orbit-src/scripts/

RUN cd /opt/orbit-src && \
    chmod +x orbit/setup/install_local_rl_stack.sh && \
    orbit/setup/install_local_rl_stack.sh /opt/orbit-src && \
    (pip uninstall torchao -y 2>/dev/null || true) && \
    rm -rf /tmp/uv-cache /root/.cache/pip /var/lib/apt/lists/*

RUN python3 - <<'PY'
import importlib.metadata as im
import json
import os
from pathlib import Path
import torch
import transformers
import swift
import vllm
print(f"torch={torch.__version__}")
print(f"transformers={transformers.__version__}")
print(f"swift={swift.__version__}")
print(f"vllm={vllm.__version__}")
print(f"affine_ms_swift_fork_dist={im.version('affine-ms-swift-fork')}")
print(f"swift_path={Path(swift.__file__).resolve()}")
manifest = json.loads((Path(os.environ['AFFINE_MS_SWIFT_FORK_ROOT']) / 'FORK_MANIFEST.json').read_text(encoding='utf-8'))
print(f"fork_manifest_upstream={manifest.get('upstream_version', '')}")
print(f"fork_manifest_fork={manifest.get('fork_version', '')}")
PY

RUN python3 -m swift.cli.rlhf --help >/dev/null

# ── Shell config ───────────────────────────────────────────────────
RUN cat > /root/.zshrc << 'EOF'
source /opt/orbit-venv/bin/activate
export PATH="/usr/local/cuda/bin:$PATH"
export LD_LIBRARY_PATH="/usr/local/cuda/lib64:${LD_LIBRARY_PATH:-}"
export HF_HOME="/data/.cache/huggingface"
export TRANSFORMERS_CACHE="/data/.cache/huggingface/hub"
export AFFINE_MS_SWIFT_FORK_ROOT="/opt/orbit-src/packages/affine_ms_swift/vendor/ms_swift_fork"
export AFFINE_MEMORYGYM_ROOT="/opt/orbit-src/repos/MemoryGym"
EOF

RUN cat > /root/.bashrc << 'EOF'
source /opt/orbit-venv/bin/activate
export PATH="/usr/local/cuda/bin:$PATH"
export LD_LIBRARY_PATH="/usr/local/cuda/lib64:${LD_LIBRARY_PATH:-}"
export HF_HOME="/data/.cache/huggingface"
export TRANSFORMERS_CACHE="/data/.cache/huggingface/hub"
export AFFINE_MS_SWIFT_FORK_ROOT="/opt/orbit-src/packages/affine_ms_swift/vendor/ms_swift_fork"
export AFFINE_MEMORYGYM_ROOT="/opt/orbit-src/repos/MemoryGym"
EOF

COPY docker/entrypoint.sh /opt/orbit/entrypoint.sh
RUN chmod +x /opt/orbit/entrypoint.sh

WORKDIR /workspace
VOLUME /data

ENTRYPOINT ["/opt/orbit/entrypoint.sh"]
CMD ["bash"]
