#!/usr/bin/env bash
# Full rental machine setup: system libs, CUDA, venv, ML stack, Docker.
# Usage: Uploaded and executed by `forge rental setup`.
# After this + clone-eval, the machine is ready for training AND evaluation.
set -eo pipefail

echo "=== System packages (libnuma, docker, screen, git, curl) ==="
apt-get update -qq && apt-get install -y -qq \
    python3 python3-pip python3-venv screen git curl \
    libnuma1 libnuma-dev docker.io gpg 2>&1 | tail -3

echo "=== CUDA toolkit (nvcc + cudart-dev) ==="
if [ -f /usr/local/cuda/bin/nvcc ]; then
    echo "CUDA toolkit already installed"
else
    curl -fsSL https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/3bf863cc.pub \
        | gpg --dearmor -o /usr/share/keyrings/cuda-archive-keyring.gpg 2>/dev/null
    echo "deb [signed-by=/usr/share/keyrings/cuda-archive-keyring.gpg] \
https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/ /" \
        > /etc/apt/sources.list.d/cuda-ubuntu2404-x86_64.list
    apt-get update -qq 2>&1 | tail -1
    apt-get install -y --no-install-recommends cuda-nvcc-12-8 cuda-cudart-dev-12-8 2>&1 | tail -3
    ln -sf /usr/local/cuda-12.8 /usr/local/cuda 2>/dev/null
    echo "CUDA_INSTALLED"
fi

echo "=== Venv + directories ==="
python3 -m venv /root/venv 2>/dev/null || true
source /root/venv/bin/activate
pip install --upgrade pip 2>&1 | tail -1
mkdir -p /root/checkpoints /root/data /root/scripts /root/logs /root/tmp

echo "=== ML training stack (torch, transformers, peft, trl, bitsandbytes) ==="
source /root/venv/bin/activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124 2>&1 | tail -3
pip install transformers datasets accelerate peft trl bitsandbytes huggingface_hub 2>&1 | tail -3

echo "=== sglang inference stack + eval deps ==="
source /root/venv/bin/activate
pip install "sglang[all]" nest_asyncio docker openai httpx 2>&1 | tail -5

echo "=== Docker images (liveweb-arena) ==="
docker pull affinefoundation/liveweb-arena:latest 2>&1 | tail -1

echo "=== Verify full stack ==="
source /root/venv/bin/activate
export PATH=/usr/local/cuda/bin:$PATH
python3 -c "
import torch; print(f'torch={torch.__version__}, cuda={torch.cuda.is_available()}, gpus={torch.cuda.device_count()}')
import sglang; print(f'sglang={sglang.__version__}')
from deep_gemm.utils.layout import get_mn_major_tma_aligned_tensor; print('deep_gemm=OK')
"

echo "=== Setup complete ==="
