#!/bin/bash
# ORBIT — Docker entrypoint for the execution image.
set -e

mkdir -p /data/{checkpoints,datasets,logs,models,.cache/huggingface}

source /opt/orbit-venv/bin/activate
export PATH="/usr/local/cuda/bin:$PATH"
export LD_LIBRARY_PATH="/usr/local/cuda/lib64:${LD_LIBRARY_PATH:-}"
export HF_HOME="/data/.cache/huggingface"
export TRANSFORMERS_CACHE="/data/.cache/huggingface/hub"

python3 -c "
import torch
import transformers
import swift
import vllm
gpus = torch.cuda.device_count()
if gpus > 0:
    name = torch.cuda.get_device_name(0)
    print(f'[AFFINE] {gpus}x {name} ready')
else:
    print('[AFFINE] WARNING: No GPUs detected')
print(f'[AFFINE] torch={torch.__version__}')
print(f'[AFFINE] transformers={transformers.__version__}')
print(f'[AFFINE] ms-swift={swift.__version__}')
print(f'[AFFINE] vllm={vllm.__version__}')
print('[AFFINE] native GKD runtime ready')
" 2>/dev/null || { echo "[AFFINE] native GKD runtime check failed" >&2; exit 1; }

exec "$@"
