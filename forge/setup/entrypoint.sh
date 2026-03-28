#!/bin/bash
# Affine Forge — Docker entrypoint for pre-built image (Method 2).
# Sets up volume directories and verifies GPU access.
set -e

# Ensure data directories exist on the volume
mkdir -p /data/{checkpoints,datasets,logs,models,.cache/huggingface}

# Activate venv
source /opt/affine-venv/bin/activate
export PATH="/usr/local/cuda/bin:$PATH"
export LD_LIBRARY_PATH="/usr/local/cuda/lib64:${LD_LIBRARY_PATH:-}"
export HF_HOME="/data/.cache/huggingface"
export TRANSFORMERS_CACHE="/data/.cache/huggingface/hub"

# Quick GPU check on startup
python3 -c "
import torch
gpus = torch.cuda.device_count()
if gpus > 0:
    name = torch.cuda.get_device_name(0)
    print(f'[AFFINE] {gpus}x {name} ready')
else:
    print('[AFFINE] WARNING: No GPUs detected')
" 2>/dev/null || echo "[AFFINE] torch GPU check failed"

exec "$@"
