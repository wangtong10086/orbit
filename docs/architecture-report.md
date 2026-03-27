# Affine Swarm 仓库架构详细报告

## 一、项目概述

**Affine Swarm** 是一个面向 [Bittensor Subnet 120 (Affine Leaderboard)](https://affine.io) 的多智能体协同训练系统，目标是通过迭代微调 **Qwen3-32B**，在所有评估环境中取得排行榜第一名。

**核心挑战**：排行榜使用所有环境的**几何平均分**排名，意味着任何一个弱项环境都会拖垮总分。系统需同时优化 6 个评估环境：GAME、NAVWORLD、LIVEWEB、SWE-INFINITE、LGC-v2、PRINT。

**当前状态**：在 NAVWORLD 和 LIVEWEB 已达到 #1，GAME 尚有 20 分差距，SWE-INFINITE 刚开始，LGC-v2 和 PRINT 暂不训练。

---

## 二、目录结构与模块职责

```
affine-swarm/
├── CLAUDE.md                 # 所有 Agent 的全局规则（每次循环必读）
├── PLAYBOOK.md               # 战略规划、优先级、当前状态
├── synth_config.json          # 数据合成状态清单（Data Agent 维护）
├── machines.json              # SSH 租用机器配置
│
├── forge/                     # 核心 Python CLI 工具包
│   ├── cli.py                 # 主 CLI 入口
│   ├── cli_data.py            # 数据管理命令
│   ├── cli_train.py           # 训练流水线命令
│   ├── cli_game.py            # GAME 环境专用命令
│   ├── cli_rental.py          # 远程 GPU 机器管理
│   ├── config.py              # 集中配置（.env 加载）
│   ├── deploy.py              # 部署工具
│   ├── compute/               # GPU 后端（Targon 无服务器 / SSH 远程）
│   ├── data/                  # 数据管道（验证、去重、格式转换）
│   ├── training/              # 训练编排（脚本生成、检查点管理）
│   └── monitoring/            # 排行榜监控
│
├── scripts/                   # 独立脚本（评估、数据生成、蒸馏）
│   ├── eval_envs.py           # 多环境评估运行器
│   ├── game_distill.py        # GAME 数据 LLM 蒸馏
│   ├── game_bots.py           # GAME 确定性机器人策略
│   ├── liveweb_*.py           # LIVEWEB 数据生成（实时/缓存/GPU）
│   ├── navworld_*.py          # NAVWORLD 数据生成与审计
│   ├── swe_*.py               # SWE-INFINITE 数据管道
│   └── merge_lora.py          # LoRA 适配器合并
│
├── .evomesh/roles/            # 多 Agent 角色定义
│   ├── strategist/ROLE.md     # 战略家：实验设计、差距分析
│   ├── trainer/ROLE.md        # 训练者：训练执行、评估
│   ├── data/ROLE.md           # 数据 Agent：数据生成与质量
│   ├── data-game/ROLE.md      # GAME 专用数据子角色
│   ├── data-swe/ROLE.md       # SWE-INFINITE 专用
│   └── data-qqr/ROLE.md       # NAVWORLD 专用
│
├── experiments/               # 实验追踪
│   ├── results.tsv            # 所有版本训练结果汇总表
│   └── v2.*.yaml              # 每个实验的配置与结果
│
├── knowledge/                 # 积累的知识库
│   ├── scoring.md             # 排行榜评分算法深度分析
│   ├── gap_analysis.md        # 竞争对手差距量化分析
│   ├── data.md                # 数据格式、生成方法、经验教训
│   ├── training.md            # 超参数演化、损失模式
│   ├── failures.md            # 失败博物馆（$80-100 成本分析）
│   └── environments/          # 各评估环境详细规格
│       ├── GAME.md            # 7 种游戏规格与策略
│       ├── NAVWORLD.md        # 导航世界格式与评分规则
│       ├── LIVEWEB.md         # 网页交互环境
│       └── SWE-INFINITE.md    # 代码修复环境
│
├── eval/                      # 各版本评估结果存档
│   └── v2.*/                  # game.json, navworld.json, liveweb.json
│
├── docs/                      # 文档
│   └── affine-system.md       # 系统架构参考
│
├── logs/                      # 日志
└── memory/                    # Agent 短期记忆
```

---

## 三、Forge CLI 工具包详解

Forge 是项目的核心命令行工具，通过 `python3 -m forge` 或 `forge` 调用。

### 3.1 排行榜监控 (`forge score`)

```bash
forge score --top 50              # 查看排行榜前 50
forge score --env GAME            # 按环境筛选
forge score --hotkey <prefix>     # 按热键前缀查找
```

实现：`forge/monitoring/leaderboard.py` — 调用 Affine API 获取实时排名。

### 3.2 数据管理 (`forge data`)

```bash
forge data merge <f1> <f2> -o out.jsonl    # 合并多个数据集
forge data analyze <file>                   # 统计分析（分布、长度、环境比例）
forge data validate <file> --env NAVWORLD   # 深度质量审计
forge data audit                            # 验证所有 canonical 文件
forge data ingest <file> --env ENV          # 暂存 → canonical（验证+去重+同步HF）
forge data canonical-upload --env all       # 同步 canonical → HuggingFace
forge data navworld-gen -n 50 --type half_day  # 生成 NAVWORLD 数据
forge data upload <file>                    # 上传任意文件到 HF
```

实现：
- `forge/cli_data.py` — CLI 命令定义
- `forge/data/sft.py` — SFT 提取、合并、分析、验证
- `forge/data/canonical_ops.py` — canonical 文件操作（schema 验证、去重、追加）
- `forge/data/navworld_gen.py` — NAVWORLD 数据生成（高德地图 API）
- `forge/data/liveweb_gen.py` — LIVEWEB 教师生成
- `forge/data/swe_ops.py` — SWE-INFINITE 操作

### 3.3 训练管理 (`forge train`)

```bash
forge train launch <dataset> \
  --hf-repo <repo> \
  --lr 2e-5 --lora-r 64 --epochs 1 \
  --batch-size 2 --grad-accum 8 \
  --max-seq-len 16384               # 启动训练

forge train prepare ENV -o dataset.jsonl   # 仅准备数据集
forge train plan ENV                        # 展示训练计划
forge train full ENV --gpu H200             # 完整流水线（提取→训练→部署）
```

实现：
- `forge/training/runner.py` — TrainingRunner 全流程编排
- `forge/training/config.py` — 训练脚本生成（HF Trainer 配置）
- `forge/training/checkpoint.py` — 检查点管理与上传

### 3.4 远程机器管理 (`forge rental`)

```bash
forge rental status [-m machine_name]       # 查看 GPU、进程、训练状态
forge rental exec "command" [-m machine]     # 远程执行命令
forge rental kill sglang|eval|training|all   # 终止进程
forge rental start-sglang <model> --tp 4     # 部署推理服务
forge rental start-eval <model> --envs GAME,NAVWORLD --samples 100
```

实现：
- `forge/cli_rental.py` — CLI 定义
- `forge/compute/ssh.py` — SSH 远程后端
- `forge/compute/targon.py` — Targon 无服务器后端
- `forge/compute/manager.py` — 统一计算管理器

### 3.5 配置系统

**`forge/config.py`** 从 `.env` 加载所有配置项：

| 配置项 | 用途 |
|--------|------|
| `API_URL` | Affine 排行榜 API |
| `HF_TOKEN` | HuggingFace 认证（私有仓库） |
| `TARGON_API_KEY` | Targon 无服务器 GPU |
| `MY_HOTKEY` / `MY_UID` | Bittensor 身份 |
| `AMAP_*_API_KEY` | NAVWORLD 高德地图 API |
| `OPENAI_API_KEY` | GPT-5.4 蒸馏 |

---

## 四、数据管道

### 4.1 数据流总览

```
数据生成（蒸馏/机器人）
        ↓
schema + 格式验证（per-env）
        ↓
去重 + 质量筛选
        ↓
canonical 文件（data/canonical/*.jsonl）
        ↓
同步到 HuggingFace（monokoco/affine-sft-data）
        ↓
Strategist 设计数据配比（experiment YAML）
        ↓
Trainer 合并 → 上传 → 训练
```

### 4.2 各环境数据格式

| 环境 | 格式 | 当前量 | 生成方法 |
|------|------|--------|----------|
| **GAME** | messages + think chain | 17,244 | 确定性机器人 + GPT-5.4 蒸馏 |
| **NAVWORLD** | messages + tool_calls | 4,330 | GPT-5.4 + 高德地图 API |
| **LIVEWEB** | messages + tool_calls | 25,205 | 确定性教师机器人 |
| **SWE-INFINITE** | messages (THOUGHT + bash) | 1,037 | GitHub PR 挖掘 + GPT-5.4 |

**通用 schema**：
```json
{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ],
  "env": "GAME",
  "score": 1.0
}
```

### 4.3 质量门控

- **Schema 验证**：必须包含 `messages`, `env`, `score`
- **格式合规**：NAVWORLD 需要 tool_calls 结构，LIVEWEB 需要 action 格式
- **序列长度**：超过训练 seq_len 的条目会被截断（有害）
- **模板多样性**：相同模式 ≤200 条
- **Think 多样性**（GAME）：唯一 `<think>` 数量 ≤3 → 丢弃

---

## 五、训练管道

### 5.1 当前配置（QLoRA，v2.25）

| 参数 | 值 |
|------|-----|
| 基座模型 | unsloth/Qwen3-32B-bnb-4bit |
| 方法 | QLoRA 4-bit NF4 |
| 学习率 | 5e-5 |
| LoRA r / alpha | 64 / 128 |
| Epoch | 1（2 会过拟合） |
| 序列长度 | 8192 |
| Batch 大小 | 2 × 4 GPU |
| 梯度累积 | 2 |
| Packing | True |
| GPU | 4× H200 (DDP) |

### 5.2 训练流程

```
1. 下载 canonical 文件 → 按实验配比合并
2. 上传到 HF 数据集仓库
3. 下载到 GPU 机器
4. 生成训练脚本（HF Trainer / Unsloth）
5. torchrun 启动分布式训练
6. 每 100 步保存检查点并自动上传 HF
7. 训练结束 → 合并 LoRA → 部署 sglang 推理
```

### 5.3 关键发现

- **学习率**：5e-5 为最优（1e-4 太激进，1e-5 收敛太慢）
- **Epoch**：严格 1 epoch（2 epoch 导致灾难性过拟合）
- **检查点**：约 84% 训练步数处的检查点最优（末尾检查点通常退化）
- **序列长度**：8192 为折中（16384 有利于 LIVEWEB 但伤害 NAVWORLD）

---

## 六、评估管道

### 6.1 评估脚本

```bash
python3 scripts/eval_envs.py \
  --base-url http://172.17.0.1:30000/v1 \
  --envs GAME NAVWORLD LIVEWEB SWE-INFINITE \
  --samples 100 \
  --concurrency 5 \
  --output-dir /root/logs
```

每个环境通过 Docker 容器运行，temperature=0 确保确定性采样。

### 6.2 评估流程

1. 部署 sglang 推理服务（检查健康状态）
2. 对每个环境并行启动评估（各一个 screen 会话）
3. 评估完成后保存 JSON 结果到 `eval/v{N}/`
4. 上传结果到 HF 模型仓库
5. 更新 `experiments/results.tsv` 和实验 YAML

### 6.3 当前最佳成绩

| 环境 | 最佳分数 | 版本 | 排名 |
|------|----------|------|------|
| GAME | 29.70 | v2.23 | 落后 ~20 分 |
| NAVWORLD | 42.84 | v2.21 | #1（领先 +10） |
| LIVEWEB | 27.76 | v2.25 | #1（领先 +8） |
| SWE-INFINITE | 未评测 | — | — |

---

## 七、多 Agent 协作系统

### 7.1 三角色架构

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Strategist  │ ←→  │   Trainer    │ ←→  │  Data Agent  │
│ (做什么+为什么) │     │ (如何训练)     │     │  (如何获取数据) │
└──────────────┘     └──────────────┘     └──────────────┘
```

**Strategist（战略家）**：
- 职责：实验设计、差距分析、审批训练
- 输出：`PLAYBOOK.md`、`experiments/*.yaml`、`knowledge/gap_analysis.md`
- 决策框架：以排名而非分数思考（decay_factor=0.5，rank 2 只有 rank 1 的 50% 权重）

**Trainer（训练者）**：
- 职责：执行训练、运行评估、报告结果
- 输出：`experiments/*.yaml`（填写结果）、`eval/v*/` 评估文件
- 可推回不可行的计划

**Data Agent（数据 Agent）**：
- 职责：数据生成、质量验证、规范化
- 输出：`synth_config.json`、`data/canonical/`、`knowledge/data.md`
- 拥有数据质量否决权

### 7.2 协作流程

```
Strategist 设计实验 YAML →
Data Agent 准备/验证数据 →
Strategist 对抗审查（写入 Trainer/Data 的 ROLE.md 挑战项）→
Trainer/Data 在自己的 ROLE.md 中回应 →
Strategist 审批或否决 →
Trainer 执行训练 →
Trainer 运行评估（100+ 样本，所有环境）→
Strategist 分析结果 → 下一个实验
```

### 7.3 文件写入权限

| 文件 | Strategist | Trainer | Data |
|------|------------|---------|------|
| 自己的 ROLE.md | ✅ | ✅ | ✅ |
| 他人 ROLE.md | ✅（仅对抗区） | ❌ | ❌ |
| PLAYBOOK.md | ✅ | 只读 | 只读 |
| experiments/*.yaml | ✅（设计） | ✅（结果） | 只读 |
| synth_config.json | 只读 | 只读 | ✅ |
| knowledge/*.md | ✅ | ✅ | ✅ |

### 7.4 通信机制

所有通信通过 git（无外部 API）：
1. **experiments/*.yaml** — 实验配置与结果
2. **synth_config.json** — 数据状态
3. **knowledge/*.md** — 共享知识
4. **.evomesh/roles/*/ROLE.md** — 对抗性审查
5. **PLAYBOOK.md** — 战略更新

---

## 八、关键知识文件

| 文件 | 内容 | 重要程度 |
|------|------|----------|
| `knowledge/scoring.md` | 评分算法 4 阶段深度分析、layer 权重、decay_factor | ⭐⭐⭐ |
| `knowledge/gap_analysis.md` | 竞争对手量化分析、ROI 排序 | ⭐⭐⭐ |
| `knowledge/data.md` | 数据格式规范、生成方法、质量教训 | ⭐⭐⭐ |
| `knowledge/training.md` | 超参数演化、损失模式、最佳实践 | ⭐⭐ |
| `knowledge/failures.md` | 失败博物馆（成本分析、避坑指南） | ⭐⭐ |
| `knowledge/environments/*.md` | 各环境详细格式、评分规则、数据问题 | ⭐⭐ |

---

## 九、实验系统

### 9.1 实验 YAML 结构

```yaml
version: v2.25
status: completed        # drafting → approved → running → completed
variable: "单一变量描述"
hypothesis: "改变 X 应该将环境 Y 的分数从 A 提升到 B，因为 Z"
data_mix:
  GAME: 9966
  NAVWORLD: 4148
  LIVEWEB: 8816
  SWE-INFINITE: 853
  total: 23783
config:
  base_model: unsloth/Qwen3-32B-bnb-4bit
  lr: 5e-5
  lora_r: 64
  epochs: 1
  seq_len: 8192
eval_plan:
  environments: [GAME, NAVWORLD, LIVEWEB]
  samples: 100
results:
  GAME: 25.26
  NAVWORLD: 40.57
  LIVEWEB: 27.76
  cost_usd: 9
```

### 9.2 核心原则

- **每次实验改变一个变量**
- **必须有量化假设**（预测分数变化）
- **必须先对抗审查**再启动训练
- **每次训练约 $9 成本** — 必须充分准备

### 9.3 方法切换触发条件

| 条件 | 触发 |
|------|------|
| SFT 瓶颈：2× 数据仅 <15% 提升 | 升级到 DPO |
| 结构性零分：连续 3+ 版本 0% | 标记为 SFT 不可学习 |
| 排名停滞：连续 3+ 版本排名不变 | 必须换方法 |

---

## 十、二次开发建议

### 10.1 添加新的评估环境

1. 在 `knowledge/environments/` 创建环境文档（格式规范、评分规则）
2. 在 `scripts/eval_envs.py` 的 `ENV_CONFIGS` 中添加环境配置
3. 在 `forge/data/` 中添加对应的数据生成/验证模块
4. 在 `synth_config.json` 中注册环境状态
5. 更新 `forge/data/canonical_ops.py` 添加验证规则

### 10.2 添加新的训练方法（如 DPO/GRPO）

1. 在 `forge/training/` 中创建新的配置生成器（参考 `config.py`）
2. 扩展 `forge/training/runner.py` 的 TrainingRunner 支持新方法
3. 在 `forge/cli_train.py` 添加命令选项
4. 当前已有 `forge/training/dpo_config.py` 骨架（未启用）

### 10.3 添加新的数据源

1. 在 `forge/data/` 创建新的生成模块
2. 在 `forge/data/canonical_ops.py` 添加格式验证
3. 在 `scripts/` 创建独立生成脚本
4. 更新 `synth_config.json` 注册新数据源
5. 确保输出符合通用 schema：`{"messages": [...], "env": "...", "score": float}`

### 10.4 添加新的 GPU 后端

1. 在 `forge/compute/` 创建新后端（继承 `base.py` 的 `ComputeBackend`）
2. 实现核心方法：`create_instance()`, `list_instances()`, `terminate()`
3. 在 `forge/compute/manager.py` 注册新后端
4. 在 `forge/cli_rental.py` 添加命令支持

### 10.5 开发注意事项

**架构原则**：
- **文件超过 500 行必须拆分**
- **重复 2 次以上的操作必须做成 CLI 命令**
- **数据质量 > 数据数量** — 格式错误比缺少数据更糟糕
- **以评估驱动开发** — 训练→评估→诊断→修复→下一轮

**Git 规范**：
- 提交格式：`{type}({scope}): {description}`
- 禁止 `git add -A` / `git add .` / `git push --force`
- 不提交：`.env`、密钥、`.claude/` 目录、`data/` 目录
- HF 仓库必须设为私有

**安全约束**：
- 不部署模型到 Chutes 或提交链上（需用户许可）
- 不提交 IP/密钥等敏感信息
- `machines.json` 中的 SSH 配置不含密码

**配置管理**：
- 所有 API 密钥通过 `.env` 管理，`forge/config.py` 集中加载
- 机器配置在 `machines.json`
- 数据状态在 `synth_config.json`
- 实验配置在 `experiments/*.yaml`

### 10.6 快速上手

```bash
# 1. 配置环境
cp .env.example .env  # 填写 API 密钥
pip install -e .

# 2. 查看排行榜
python3 -m forge score --top 10

# 3. 查看 GPU 机器状态
forge rental status

# 4. 分析数据集
forge data analyze data/canonical/game.jsonl

# 5. 验证数据质量
forge data validate data/canonical/navworld.jsonl --env NAVWORLD

# 6. 查看最新实验
cat experiments/results.tsv
cat experiments/v2.27.yaml

# 7. 启动训练（需要 GPU 机器）
forge train launch data/combined.jsonl \
  --hf-repo monokoco/affine-sft-data \
  --lr 5e-5 --lora-r 64 --epochs 1
```

---

## 十一、竞争态势与战略方向

### 当前排名（Block 7834920）

| 排名 | 矿工 | GAME | NW | LW | SWE-I |
|------|-------|------|-----|-----|-------|
| #1 | EdmondMillion | 46.22 | 32.81 | 18.69 | 8.25 |
| #2 | luis1027 | 48.22 | 20.07 | 17.90 | 4.82 |
| **我们** | — | 29.70 | **42.84** | **27.76** | — |

### 战略重点

1. **GAME 空间游戏突破**：hex/othello/clobber 贡献 19 分，当前 0%。v2.27 计划用 full fine-tune 解决
2. **保持 NW/LW 领先**：已 #1，避免回退
3. **SWE-INFINITE 启动**：1037 条数据就绪，Go 语言为主
4. **Layer 天花板**：当前只覆盖 4/6 环境（L4），竞争者有 L6（32× 权重）

---

*报告生成时间：2026-03-27*
