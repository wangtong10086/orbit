---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-28T08:00
---

# v2.28 启动失败 — nvcc not found

## 错误
DeepSpeed JIT 编译需要 nvcc: `FileNotFoundError: /usr/bin/nvcc`

## 修复
```bash
# Option 1: 安装 CUDA toolkit
apt-get update && apt-get install -y cuda-toolkit-12-0

# Option 2: 如果 nvcc 在别的路径
find / -name nvcc 2>/dev/null
export CUDA_HOME=/path/to/cuda

# Option 3: 预编译 DeepSpeed ops
DS_BUILD_OPS=1 pip install deepspeed --force-reinstall
```

修复后重启训练。
