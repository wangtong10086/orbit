# Affine Forge — Training Environment (Method 2: Pre-built image)
#
# This image includes the full training + inference stack so Targon
# deployments start with zero setup time. Model weights and datasets
# are still cached on the /data volume.
#
# Build:
#   docker build -t <registry>/affine-forge:latest -f forge/setup/Dockerfile .
#
# Push:
#   docker push <registry>/affine-forge:latest
#
# Usage on Targon SSH deployment:
#   Create deployment with image: <registry>/affine-forge:latest
#   Volume mounted at /data is used for models, datasets, checkpoints.

FROM nvidia/cuda:12.4.1-devel-ubuntu22.04

LABEL maintainer="affine-forge"
LABEL description="Affine training environment with ms-swift, DeepSpeed, sglang"

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# ─── System packages ──────────────────────────────────────────────
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    build-essential git curl wget unzip \
    zsh tmux screen htop jq \
    openssh-server openssh-client rsync \
    libnuma1 libnuma-dev \
    software-properties-common \
    ca-certificates gnupg \
    && rm -rf /var/lib/apt/lists/*

# ─── Docker client (for DinD when privileged) ─────────────────────
RUN install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu jammy stable" > /etc/apt/sources.list.d/docker.list && \
    apt-get update -qq && \
    apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin && \
    rm -rf /var/lib/apt/lists/*

# ─── uv (fast Python package manager) ─────────────────────────────
ENV UV_INSTALL_DIR=/usr/local/bin
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# ─── Python 3.11 via uv ───────────────────────────────────────────
RUN uv python install 3.11

# ─── Python venv + ML stack ───────────────────────────────────────
ENV VIRTUAL_ENV=/opt/affine-venv
RUN uv venv $VIRTUAL_ENV --python 3.11
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Install PyTorch with CUDA 12.4
RUN uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# Training stack
COPY forge/setup/requirements.txt /tmp/requirements.txt
RUN uv pip install -r /tmp/requirements.txt && rm /tmp/requirements.txt

# flash-attn must be after torch (build dependency)
RUN uv pip install flash-attn --no-build-isolation

# ─── Node.js 20 LTS ───────────────────────────────────────────────
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

# ─── Neovim + LazyVim ─────────────────────────────────────────────
RUN curl -fsSL https://github.com/neovim/neovim/releases/latest/download/nvim-linux-x86_64.tar.gz \
    | tar xzf - --strip-components=1 -C /usr/local && \
    git clone --depth 1 https://github.com/LazyVim/starter /root/.config/nvim && \
    rm -rf /root/.config/nvim/.git

# ─── Zsh + Oh My Zsh ──────────────────────────────────────────────
RUN sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" \
    --unattended 2>/dev/null || true

# ─── Shell configuration ──────────────────────────────────────────
RUN cat > /root/.zshrc << 'EOF'
export ZSH="$HOME/.oh-my-zsh"
ZSH_THEME="robbyrussell"
plugins=(git docker python)
[ -f $ZSH/oh-my-zsh.sh ] && source $ZSH/oh-my-zsh.sh
# Activate training env
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

# ─── Entrypoint: create data dirs + verify ─────────────────────────
COPY forge/setup/entrypoint.sh /opt/affine/entrypoint.sh
RUN chmod +x /opt/affine/entrypoint.sh

WORKDIR /workspace
VOLUME /data

ENTRYPOINT ["/opt/affine/entrypoint.sh"]
CMD ["bash"]
