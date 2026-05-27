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
    print(f'[ORBIT] {gpus}x {name} ready')
else:
    print('[ORBIT] WARNING: No GPUs detected')
print(f'[ORBIT] torch={torch.__version__}')
print(f'[ORBIT] transformers={transformers.__version__}')
print(f'[ORBIT] ms-swift={swift.__version__}')
print(f'[ORBIT] vllm={vllm.__version__}')
print('[ORBIT] native GKD runtime ready')
" 2>/dev/null || { echo "[ORBIT] native GKD runtime check failed" >&2; exit 1; }

exec "$@"
