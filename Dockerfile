# Affine Forge — Execution Runtime Image
#
# Build:
#   docker build -t wangtong123/affine-forge:latest .
#
# Push:
#   docker push wangtong123/affine-forge:latest

FROM nvidia/cuda:12.4.1-devel-ubuntu22.04

LABEL maintainer="affine-forge"
LABEL description="Affine execution environment with ms-swift, DeepSpeed, sglang"

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    build-essential git curl wget unzip \
    zsh tmux screen htop jq \
    openssh-server openssh-client rsync \
    libnuma1 libnuma-dev \
    software-properties-common \
    ca-certificates gnupg \
    && rm -rf /var/lib/apt/lists/*

ENV UV_INSTALL_DIR=/usr/local/bin
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

RUN uv python install 3.11

ENV VIRTUAL_ENV=/opt/affine-venv
RUN uv venv $VIRTUAL_ENV --python 3.11
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY docker/requirements-exec.txt /tmp/requirements-exec.txt
RUN uv pip install --no-cache torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124 \
    && (uv pip install --no-cache flash-attn --no-build-isolation 2>/dev/null || \
        echo "WARN: flash-attn wheel not available, skipping (will use sdpa fallback)") \
    && uv pip install --no-cache -r /tmp/requirements-exec.txt \
    && uv pip install --no-cache torch torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/cu124 --reinstall \
    && rm -rf /tmp/* /root/.cache

RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://github.com/neovim/neovim/releases/latest/download/nvim-linux-x86_64.tar.gz \
    | tar xzf - --strip-components=1 -C /usr/local && \
    git clone --depth 1 https://github.com/LazyVim/starter /root/.config/nvim && \
    rm -rf /root/.config/nvim/.git

RUN sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" \
    --unattended 2>/dev/null || true

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
