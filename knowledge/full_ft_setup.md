# Full Fine-Tuning Setup — Qwen3-32B (v2.28+)

## 训练框架

### 主框架：ms-swift 4.0.2
- 竞争对手使用，社区成熟
- 自动处理 chat template、loss masking、tool_calls
- 命令：`NPROC_PER_NODE=8 swift sft --model ... --dataset ...`

### 备选框架：TRL SFTTrainer (HuggingFace)
- 对多轮 tool calling 兼容性更好（无严格交替要求）
- 脚本：`/data/scripts/train_trl.py`
- 当 ms-swift 过滤过多时可切换

## 持久卷 /data 布局

```
/data/                              # 持久卷 (2TB, 容器重建不丢失)
├── venv/                           # Python venv
├── .env                            # HF_TOKEN, AMAP keys
├── models/Qwen3-32B/              # 基础模型 (~65GB, 17 shards)
├── datasets/
│   ├── combined_shuffled.jsonl    # 训练用（shuffle + 只含 messages/tools）
│   ├── combined_trl.jsonl         # 原始合并（含 env 等元数据列）
│   └── canonical/                 # HF 各环境原始文件
├── checkpoints/                   # 训练输出
├── logs/                          # 训练日志
├── scripts/                       # 启动脚本
│   ├── launch_msswift_v2.sh
│   ├── launch_trl.sh
│   └── train_trl.py
└── configs/
    └── ds_zero3.json              # DeepSpeed ZeRO-3 配置
```

## 数据准备（关键！）

### ms-swift 数据要求
1. **只含 `messages` 和 `tools` 字段** — 不能有 env/source/game 等额外列，否则 datasets CastError
2. **必须 shuffle** — 同类数据连续会导致 schema 推断失败
3. **tool_calls 格式必须标准 OpenAI** — `assistant.tool_calls = [{id, type, function: {name, arguments}}]`
4. **tool 消息必须有 tool_call_id** — 与 assistant.tool_calls 中的 id 配对
5. **少量 assertion error 可接受** — <1% 过滤率正常

### 数据准备脚本
```python
import json, random
data = []
with open('combined.jsonl') as f:
    for line in f:
        d = json.loads(line.strip())
        entry = {'messages': d['messages']}
        if d.get('tools'):
            entry['tools'] = d['tools']
        data.append(entry)
random.seed(42)
random.shuffle(data)
with open('combined_shuffled.jsonl', 'w') as f:
    for d in data:
        f.write(json.dumps(d, ensure_ascii=False) + '\n')
```

### 数据来源（HF repo: monokoco/affine-sft-data）
| 环境 | 文件 | 行数 | 注意事项 |
|------|------|------|---------|
| GAME | game.jsonl | 103592 | 纯文本对话，无 tool_calls，v18 rebalance 计划降至 59k |
| MemoryGym | memorygym.jsonl | 20000 | v4g 纯文本格式（XML tool_call in content） |
| LIVEWEB | liveweb.jsonl | 19776 | 3-msg single-step 格式，ms-swift 兼容 |
| NAVWORLD | navworld.jsonl | 10006 | 多轮 OpenAI tool calling, hermes agent template |
| SWE-I | swe_infinite.jsonl | 1735 | Go ~95%, THOUGHT+bash |

**注意**：根目录和 canonical/ 下同名文件可能不同版本。NW 必须用 `canonical/navworld.jsonl`（修复后的多轮版本）。

## 基础设施 (m3: 8×H200)

### 环境
- **GPU**: 8× NVIDIA H200 (143GB each)
- **Driver**: 570.195.03
- **CUDA toolkit**: 12.8 (`/usr/local/cuda/bin/nvcc`)
- **Venv**: `/data/venv/` — torch 2.9.1+cu128, ms-swift 4.0.2, deepspeed, trl 1.0.0rc1
- **flash-attn**: 需单独安装（编译慢），未装时用 sdpa fallback

### 容器重建恢复流程
```bash
forge remote -m m3 setup    # 重装系统包 + CUDA, /data 上的 venv/model/data 自动复用
```

### DeepSpeed ZeRO-3 配置
- 必须 ZeRO-3（ZeRO-2 OOM: 132/143GB）
- CPU offload（param + optimizer）
- GPU 峰值 ~130-136GB（ms-swift）或 ~75GB（自写脚本）
- Checkpoint ~400GB（含 optimizer states），save_steps=100

## 训练参数（v2.28 验证）

```
method: Full SFT (NOT QLoRA)
model: Qwen/Qwen3-32B (bf16)
deepspeed: ZeRO-3 + CPU offload
batch_size: 1 per GPU
grad_accum: 4
effective_batch: 1 × 4 × 8GPU = 32
lr: 2e-5 cosine, warmup 3%
seq_len: 32768
epochs: 1
save_steps: 100
save_total_limit: 5
```

## 已知问题和教训

### 1. 训练时不上传 HF
v2.27 教训：5×400GB checkpoint 同时上传导致 OOM 崩溃。训练完成后再上传。

### 2. CUDA toolkit 必须安装
DeepSpeed JIT 编译需要 nvcc。setup 中 CUDA 安装是必须步骤。
Launch 脚本必须设置：`export CUDA_HOME=/usr/local/cuda && export PATH=/usr/local/cuda/bin:$PATH`

### 3. ms-swift 数据格式严格
- 额外列 → CastError（需去掉 env/source 等列）
- 数据不 shuffle → schema 推断失败
- tool 无 tool_call_id → assertion error
- assistant 无 tool_calls 但后跟 tool → 过滤

### 4. 容器会被重建
Targon 容器随时可能重建。所有持久化数据必须放 /data。setup 脚本自动跳过已存在的组件。

## CLI 工具

```bash
forge remote -m m3 setup              # 一键初始化
forge train data-summary -m m3        # 数据分析
forge train launch -m m3 --save-steps 100  # 启动训练
forge train monitor -m m3             # 监控
forge train stop -m m3                # 停止
```
