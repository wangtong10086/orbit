#!/bin/bash
# Affine Forge — Docker entrypoint for the execution image.
set -e

mkdir -p /data/{checkpoints,datasets,logs,models,.cache/huggingface}

source /opt/affine-venv/bin/activate
export PATH="/usr/local/cuda/bin:$PATH"
export LD_LIBRARY_PATH="/usr/local/cuda/lib64:${LD_LIBRARY_PATH:-}"
export HF_HOME="/data/.cache/huggingface"
export TRANSFORMERS_CACHE="/data/.cache/huggingface/hub"

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
