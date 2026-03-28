# Training Storage Design — /data 持久卷

## 目录结构

```
/data/                          # 持久卷 (2TB, 容器重建不丢失)
├── venv/                       # Python venv (torch + ms-swift + deps)
├── .env                        # HF_TOKEN, AMAP keys
├── models/
│   └── Qwen3-32B/             # 基础模型权重 (不变, ~65GB)
├── datasets/
│   ├── game.jsonl             # 各环境原始数据
│   ├── navworld.jsonl
│   ├── liveweb.jsonl
│   ├── swe_infinite.jsonl
│   ├── memorygym.jsonl
│   └── combined.jsonl         # 合并后训练数据
├── checkpoints/
│   └── v2.28/                 # 按版本存放
│       ├── checkpoint-50/
│       ├── checkpoint-100/
│       └── ...
├── logs/
│   ├── train_v2.28.log
│   └── eval_v2.28_*.log
├── scripts/                   # 启动脚本
│   └── launch_swift.sh
└── eval/                      # 评测结果
    └── v2.28/

/root/                         # 容器临时空间 (重建后清空)
├── venv -> /data/venv         # 全部是 symlink
├── models -> /data/models
├── data -> /data/datasets
├── checkpoints -> /data/checkpoints
├── logs -> /data/logs
├── .env -> /data/.env
└── scripts -> /data/scripts
```

## Checkpoint 管理规则

### 存放路径
- `/data/checkpoints/v{VERSION}/checkpoint-{STEP}/`
- ms-swift 默认输出到 `--output_dir /data/checkpoints`
- ms-swift 自动创建子目录 `v1-{timestamp}/checkpoint-{step}/`

### 自动上传 HF
- **训练完成后** 上传（不在训练中上传，避免 OOM 崩溃）
- 上传到 `monokoco/affine-qwen3-32b-v{VERSION}-checkpoints`
- 只上传模型文件（*.safetensors, *.json），不上传 optimizer states
- 命令: `forge train upload -m <machine> --version v2.28 --checkpoint 50`

### 清理规则
- `save_total_limit=5` — ms-swift 自动保留最近 5 个 checkpoint
- 训练完成后，eval 确定最佳 checkpoint，删除其余
- 上传 HF 后可清理本地
- `/data` 2TB 容量，每 checkpoint ~400GB (含 optimizer)，最多 ~5 个

### 重要：不在训练时上传
教训：v2.27 在训练时同时上传 2TB checkpoints 到 HF，导致 OOM 崩溃。
上传必须在训练停止后进行。

## 模型版本管理

### 命名规则
- HF 模型 repo: `monokoco/affine-qwen3-32b-v{VERSION}`
- HF checkpoint repo: `monokoco/affine-qwen3-32b-v{VERSION}-checkpoints`

### 本地路径
- 基础模型: `/data/models/Qwen3-32B/` (共享, 不变)
- 训练输出: `/data/checkpoints/v1-{timestamp}/` (ms-swift 自动命名)
- 评测用模型: sglang 直接加载 checkpoint 目录

## CLI 命令一览

```bash
# 机器管理
forge remote -m m3 setup          # 一键初始化 (利用 /data 缓存)
forge remote -m m3 status         # 查看机器状态

# 训练流程
forge train data-summary -m m3    # 数据质量检查
forge train launch -m m3          # 启动训练
forge train monitor -m m3         # 监控训练进度
forge train stop -m m3            # 停止训练

# 评测 (TODO)
forge train eval -m m1 --model /data/checkpoints/best/
```
