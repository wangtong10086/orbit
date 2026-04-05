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
# This image packages the execution plane only. Dependencies are managed
# via pyproject.toml [project.optional-dependencies] exec extra.

FROM nvidia/cuda:12.4.1-devel-ubuntu22.04

LABEL maintainer="orbit"
LABEL description="Affine execution plane — ms-swift, DeepSpeed, sglang"

ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ARG http_proxy
ARG https_proxy
ARG no_proxy

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV HTTP_PROXY=${HTTP_PROXY:-${http_proxy}}
ENV HTTPS_PROXY=${HTTPS_PROXY:-${https_proxy}}
ENV NO_PROXY=${NO_PROXY:-${no_proxy}}
ENV http_proxy=${http_proxy:-${HTTP_PROXY}}
ENV https_proxy=${https_proxy:-${HTTPS_PROXY}}
ENV no_proxy=${no_proxy:-${NO_PROXY}}

RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    build-essential git curl wget unzip \
    zsh tmux screen htop jq \
    openssh-server openssh-client rsync \
    libnuma1 libnuma-dev \
    software-properties-common \
    ca-certificates gnupg \
    && rm -rf /var/lib/apt/lists/*

# ── Python tooling ──────────────────────────────────────────────────
ENV UV_INSTALL_DIR=/usr/local/bin
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
RUN uv python install 3.11

ENV VIRTUAL_ENV=/opt/affine-venv
RUN uv venv $VIRTUAL_ENV --python 3.11
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# ── Force HuggingFace downloads (not ModelScope) ───────────────────
ENV USE_MODELSCOPE=False
ENV USE_HF=1
ENV HF_HOME="/data/.cache/huggingface"
ENV TRANSFORMERS_CACHE="/data/.cache/huggingface/hub"
# Prefer a less fragmentation-prone CUDA allocator for large local full-param runs.
ENV PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"

# ── PyTorch (CUDA 12.4) — installed first before project deps ──────
RUN uv pip install --no-cache torch torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/cu124

# ── flash-attn (optional, may fail due to ABI mismatch) ────────────
RUN uv pip install --no-cache flash-attn --no-build-isolation 2>/dev/null || \
    echo "WARN: flash-attn wheel not available, training will use sdpa fallback"

# ── Project source + execution-plane dependencies ──────────────────
COPY pyproject.toml /opt/affine-src/pyproject.toml
COPY orbit/ /opt/affine-src/orbit/
COPY scripts/ /opt/affine-src/scripts/
RUN cd /opt/affine-src && uv pip install --no-cache ".[exec]" \
    && uv pip install --no-cache "transformers==4.51.3" \
    && uv pip install --no-cache torch torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/cu124 --reinstall \
    && pip uninstall torchao -y 2>/dev/null || true \
    && rm -rf /tmp/* /root/.cache/pip

# ── Dev tools (Node.js, Neovim, Zsh) ──────────────────────────────
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://github.com/neovim/neovim/releases/latest/download/nvim-linux-x86_64.tar.gz \
    | tar xzf - --strip-components=1 -C /usr/local && \
    git clone --depth 1 https://github.com/LazyVim/starter /root/.config/nvim && \
    rm -rf /root/.config/nvim/.git

RUN sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" \
    --unattended 2>/dev/null || true

# ── Shell config ───────────────────────────────────────────────────
RUN cat > /root/.zshrc << 'EOF'
export ZSH="$HOME/.oh-my-zsh"
ZSH_THEME="robbyrussell"
plugins=(git docker python)
[ -f $ZSH/oh-my-zsh.sh ] && source $ZSH/oh-my-zsh.sh
source /opt/affine-venv/bin/activate
export PATH="/usr/local/cuda/bin:$PATH"
export LD_LIBRARY_PATH="/usr/local/cuda/lib64:${LD_LIBRARY_PATH:-}"
export HF_HOME="/data/.cache/huggingface"
export TRANSFORMERS_CACHE="/data/.cache/huggingface/hub"
EOF

RUN cat > /root/.bashrc << 'EOF'
source /opt/affine-venv/bin/activate
export PATH="/usr/local/cuda/bin:$PATH"
export LD_LIBRARY_PATH="/usr/local/cuda/lib64:${LD_LIBRARY_PATH:-}"
export HF_HOME="/data/.cache/huggingface"
export TRANSFORMERS_CACHE="/data/.cache/huggingface/hub"
EOF

COPY docker/entrypoint.sh /opt/affine/entrypoint.sh
RUN chmod +x /opt/affine/entrypoint.sh

WORKDIR /workspace
VOLUME /data

ENTRYPOINT ["/opt/affine/entrypoint.sh"]
CMD ["bash"]
