# Affine Swarm 架构详细报告

## 一、项目概述

**Affine Swarm** 是一个面向 [Bittensor Subnet 120 (Affine Leaderboard)](https://affine.io) 的多智能体协同训练系统，目标是通过迭代微调 **Qwen3-32B**，在所有评估环境中取得排行榜第一名。

**核心挑战**：排行榜使用所有环境的**几何平均分**排名，任何一个弱项环境都会拖垮总分。系统需同时优化多个评估环境：GAME、NAVWORLD、LIVEWEB、SWE-SYNTH、LGC-v2、PRINT。

---

## 二、三层架构总览

系统采用严格分层的三层架构，每层只依赖下层，不存在跨层或反向依赖：

```text
┌─────────────────────────────────────────────────────────┐
│  Layer 2 — Agent（自主智能体）                            │
│  StrategistAgent · TrainerAgent · DataAgent               │
│  EvolutionLoop（sense → plan → act → reflect）            │
├─────────────────────────────────────────────────────────┤
│  Layer 1 — Pipeline（应用流水线）                          │
│  DataPipeline · Evaluator · ExperimentTracker             │
├─────────────────────────────────────────────────────────┤
│  Layer 0 — Foundation（基础模块，零交叉依赖）              │
│  env/（EnvHub + GEM + Sandbox）                           │
│  prompt/（PromptBuilder + Templates）                     │
│  training/（SwiftConfig + Backend + Executor）            │
└─────────────────────────────────────────────────────────┘
```

**设计原则**：
- Layer 0 各模块之间零依赖，只依赖 Python 标准库
- Layer 1 组合 Layer 0 的能力为可复用的流水线
- Layer 2 编排 Layer 1 流水线实现自主训练循环

---

## 三、Layer 0 — Foundation

### 3.1 环境模块 (`forge/env/`)

三个独立接口，参考 ROCK 架构：

| 接口 | 文件 | 职责 |
|------|------|------|
| **Data API** | `base.py` | 离线 SFT 数据验证：`validate_entry()`, `clean_entry()`, `deep_validate()` |
| **GEM API** | `gem.py` | 交互式环境协议：`reset()` → `step(action)` → `close()` |
| **Sandbox API** | `sandbox.py` | 运行时生命周期：`start()` → `execute(cmd)` → `stop()` |

**核心类型**：

| 类型 | 所在文件 | 用途 |
|------|----------|------|
| `EnvSpec` | `base.py` | 环境元数据：名称、版本、权重、有效角色 |
| `EnvProtocol` | `base.py` | 数据验证器接口 |
| `GemEnv` | `gem.py` | 交互式环境基类（Gymnasium 风格） |
| `Observation` | `gem.py` | Agent 可观察状态 |
| `StepResult` | `gem.py` | 步骤结果（observation, reward, terminated, truncated, info） |
| `SandboxConfig` | `sandbox.py` | 容器配置（镜像、内存、GPU、超时） |
| `Sandbox` | `sandbox.py` | 运行时管理器 |

**双重注册表** (`registry.py`)：

| 注册表 | 用途 |
|--------|------|
| `EnvRegistry` | 向后兼容的数据验证器注册表（`@register`, `make`, `list_envs`） |
| `EnvHub` | 统一枢纽：`make_data()`, `make_gem()`, `list_all()`, `has_gem()` |

**Per-environment 实现**：

| 文件 | 数据验证器 | GEM 环境 | 关键规则 |
|------|-----------|----------|----------|
| `game.py` | `GameEnv` | `GameGemEnv` | weight=3.0, ≥3 msgs, system first |
| `navworld.py` | `NavworldEnv` | `NavworldGemEnv` | ≥7 msgs, ≥3 tool calls, final ≥200 chars |
| `swe.py` | `SweEnv` | `SweGemEnv` | ≥4 msgs, system first |
| `liveweb.py` | `LivewebEnv` | `LivewebGemEnv` | ≥3 msgs, has assistant, allows tool role |
| `lgc.py` | `LgcEnv` | `LgcGemEnv` | Exactly 2 msgs, balanced think tags |
| `print_env.py` | `PrintEnv` | `PrintGemEnv` | Exactly 2 msgs, answer after think |

### 3.2 提示词引擎 (`forge/prompt/`)

| 文件 | 导出 | 用途 |
|------|------|------|
| `builder.py` | `PromptBuilder`, `Message` | Fluent API 构建 OpenAI 格式消息列表 |
| `tools.py` | `load_tools`, `tool_names`, `get_tool_schema` | 从模板目录加载工具 JSON |
| `templates/` | `.md` + `.json` 文件 | 各环境系统提示词和工具 schema |

### 3.3 训练后端 (`forge/training/`)

基于 [ms-swift](https://github.com/modelscope/ms-swift) 4.x，支持多种训练模式：

| 文件 | 导出 | 用途 |
|------|------|------|
| `config.py` | `SwiftConfig`, `TrainType`, `TunerType`, `RlhfType` | 全部训练超参数配置 |
| `backend.py` | `TrainBackend` | 后端协议：`generate_script()`, `validate_config()` |
| `sft.py` | `SwiftBackend` | ms-swift SFT/RLHF 实现 |
| `model.py` | `merge_lora_adapter`, `get_hf_latest_revision` | 模型管理工具 |
| `executor/` | `ExecutorProtocol`, `TargonExecutor`, `RemoteExecutor` | 计算后端 |

**支持的训练模式**：

| 模式 | 说明 |
|------|------|
| SFT + LoRA | QLoRA 4-bit, LoRA r=64, α=128 |
| SFT + Full | 全参数微调（需 DeepSpeed ZeRO-3） |
| DPO/GRPO/KTO/CPO/SimPO/ORPO/PPO | RLHF 算法（`--train-type rlhf --rlhf-type <type>`） |

**`SwiftConfig` 关键字段**：

| 分组 | 字段 | 默认值 |
|------|------|--------|
| 模型 | `model`, `dtype`, `attn_impl` | Qwen3-32B, bfloat16, flash_attn |
| 方法 | `train_type`, `rlhf_type` | sft, dpo |
| 调参 | `tuner_type`, `lora_rank`, `lora_alpha` | lora, 64, 128 |
| 量化 | `quant_method`, `quant_bits` | bnb, 4 |
| 超参 | `learning_rate`, `num_train_epochs`, `batch_size` | 1e-4, 1, 2 |
| 分布式 | `deepspeed`, `num_gpus`, `gradient_checkpointing` | None, 1, True |
| 保存 | `output_dir`, `save_steps`, `push_to_hub` | /root/checkpoints, 100, False |

---

## 四、Layer 1 — Pipeline

### 4.1 数据流水线 (`forge/pipeline/data.py`)

```text
数据生成 → DataPipeline.ingest()
  → clean_entry()（per-env 清洗）
  → validate_entry()（per-env 验证）
  → 去重
  → 存储（canonical 文件）
  → 导出到 HuggingFace
```

| 类 | 方法 | 说明 |
|----|------|------|
| `DataPipeline` | `ingest(records, env)` | 完整摄入流程 |
| `DataPipeline` | `audit(env)` | 审计 canonical 数据质量 |
| `IngestReport` | — | 摄入结果报告（accepted, rejected, duplicated） |

### 4.2 评估器 (`forge/pipeline/eval.py`)

| 类 | 方法 | 说明 |
|----|------|------|
| `Evaluator` | `evaluate(model, envs, samples)` | 多环境并行评估 |
| `Evaluator` | `compute_geo_mean(results)` | 计算几何平均分 |
| `EvalReport` | — | 评估报告（per-env 分数 + geo mean） |
| `EnvResult` | — | 单环境评估结果 |

### 4.3 实验追踪器 (`forge/pipeline/experiment.py`)

| 类 | 方法 | 说明 |
|----|------|------|
| `ExperimentTracker` | `create(config)` | 创建新实验 YAML |
| `ExperimentTracker` | `update_status(id, status)` | 更新实验状态 |
| `ExperimentTracker` | `record_results(id, results)` | 记录评估结果 |
| `Experiment` | — | 实验数据类（version, status, data_mix, config, results） |

---

## 五、Layer 2 — Agent

### 5.1 Agent 协议 (`forge/agent/base.py`)

所有 Agent 遵循统一的 sense → plan → act → reflect 循环：

```python
class AgentProtocol:
    def sense(self) -> dict:         # 感知当前状态
    def plan(self, state) -> list:   # 规划行动
    def act(self, actions) -> dict:  # 执行行动
    def reflect(self, result) -> dict: # 反思结果
```

### 5.2 三角色 Agent

```text
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Strategist  │ ←→  │   Trainer    │ ←→  │  Data Agent  │
│ (WHAT + WHY) │     │  (HOW train) │     │  (HOW data)  │
└──────────────┘     └──────────────┘     └──────────────┘
```

| Agent | 类 | 职责 |
|-------|------|------|
| Strategist | `StrategistAgent` | 差距分析、实验设计、方法切换、审批 |
| Trainer | `TrainerAgent` | 验证实验、编排训练→评估、报告结果 |
| Data Agent | `DataAgent` | 数据准备、质量审计、充分性检查 |

**协作流程**：
```text
Strategist 设计实验 → Data Agent 准备数据 → Strategist 审批 →
Trainer 执行训练 → Trainer 运行评估 → Strategist 分析结果
```

### 5.3 自进化循环 (`forge/agent/loop.py`)

`EvolutionLoop` 编排完整的训练迭代：

```text
1. analyze()  — Strategist 执行差距分析
2. design()   — Strategist 设计下一个实验
3. prepare()  — Data Agent 准备数据
4. train()    — Trainer 执行训练
5. evaluate() — Trainer 运行多环境评估
6. reflect()  — Strategist 分析结果，更新知识
7. repeat
```

---

## 六、依赖关系图

```text
Layer 2: agent/strategist ─→ pipeline/experiment
         agent/trainer    ─→ pipeline/eval, training/sft
         agent/data_agent ─→ pipeline/data, env/registry
         agent/loop       ─→ agent/*

Layer 1: pipeline/data    ─→ env/registry
         pipeline/eval    ─→ env/registry
         pipeline/experiment ─→ (stdlib: yaml, pathlib)

Layer 0: env/sandbox.py   ─→ (stdlib: dataclasses, enum)
         env/gem.py       ─→ env/base (EnvSpec)
         env/registry.py  ─→ env/base, env/gem
         env/*.py         ─→ env/base, env/gem, env/registry
         prompt/*         ─→ (stdlib only)
         training/*       ─→ (stdlib only, except model.py)
```

---

## 七、CLI 命令参考

### 7.1 排行榜监控 (`forge score`)

```bash
forge score --top 50              # 查看排行榜前 50
forge score --env GAME            # 按环境筛选
```

### 7.2 数据管理 (`forge data`)

```bash
forge data audit                                    # 验证所有 canonical 文件
forge data validate <file> --env NAVWORLD           # 深度质量审计
forge data ingest <file> --env ENV --source SRC     # 暂存 → canonical
forge data analyze <file>                           # 统计分析
forge data merge <f1> <f2> -o out.jsonl             # 合并数据集
forge data upload <file>                            # 上传到 HF
```

### 7.3 训练管理 (`forge train`)

```bash
# SFT + LoRA（默认）
forge train launch data.jsonl \
  --dataset-repo <repo> \
  --lr 1e-4 --lora-r 64 --max-length 8192

# SFT + 全参数微调
forge train launch data.jsonl \
  --dataset-repo <repo> \
  --tuner-type full --no-quant --deepspeed zero3

# RLHF (DPO)
forge train launch data.jsonl \
  --dataset-repo <repo> \
  --train-type rlhf --rlhf-type dpo

# RLHF 快捷命令
forge train rlhf-launch data.jsonl \
  --dataset-repo <repo> \
  --rlhf-type grpo --sft-adapter <adapter>

# 其他命令
forge train prepare ENV -o dataset.jsonl    # 仅准备数据集
forge train plan ENV                         # 展示训练计划
forge train full ENV --gpu H200              # 完整流水线
```

### 7.4 GPU 管理 (`forge rental`)

```bash
forge rental status                          # 查看 GPU 状态
forge rental kill sglang|eval|training|all   # 终止进程
forge rental start-sglang <model> --tp 4     # 部署推理服务
forge rental start-eval <model> --envs GAME,NAVWORLD --samples 100
```

---

## 八、数据格式规范

### 通用 Schema

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

### 环境特殊要求

| 环境 | 特殊字段 | 验证规则 |
|------|----------|----------|
| GAME | `<think>` chain in assistant | ≥3 msgs, system 在首位, weight=3.0 |
| NAVWORLD | `tool_calls` in assistant | ≥7 msgs, ≥3 tool calls, 最终回复 ≥200 chars |
| LIVEWEB | `tool_calls` + tool role | ≥3 msgs, 必须有 assistant, 允许 tool role |
| SWE-SYNTH | THOUGHT + bash patterns | ≥4 msgs, system 在首位 |
| LGC-v2 | balanced `<think>` tags | Exactly 2 msgs |
| PRINT | think → answer pattern | Exactly 2 msgs |

---

## 九、实验系统

### 实验 YAML 结构

```yaml
version: v2.27
status: running          # drafting → approved → running → completed
variable: "单一变量描述"
hypothesis: "改变 X 应该将环境 Y 的分数从 A 提升到 B，因为 Z"
data_mix:
  GAME: 10000
  NAVWORLD: 4300
  LIVEWEB: 8800
  SWE-SYNTH: 1000
  total: 24100
config:
  base_model: Qwen/Qwen3-32B
  train_type: sft
  tuner_type: full
  deepspeed: zero3
  lr: 5e-5
  epochs: 1
  max_length: 32768
  num_gpus: 8
eval_plan:
  environments: [GAME, NAVWORLD, LIVEWEB, SWE-SYNTH]
  samples: 100
results:
  GAME: null
  NAVWORLD: null
  cost_usd: 9
```

### 方法切换触发条件

| 条件 | 触发动作 |
|------|----------|
| SFT 瓶颈：2× 数据仅 <15% 提升 | 升级到 DPO |
| 结构性零分：连续 3+ 版本 0% | 标记为 SFT 不可学习 |
| 排名停滞：连续 3+ 版本排名不变 | 切换训练方法 |

---

## 十、二次开发指南

### 添加新评估环境

1. `forge/env/` 中创建 `<newenv>.py`，实现 `EnvProtocol` 和 `GemEnv`
2. 使用 `@register` 装饰器注册到 `EnvRegistry` 和 `EnvHub`
3. `forge/prompt/templates/` 中添加系统提示词和工具 schema
4. `knowledge/environments/` 中添加环境文档
5. 更新 `synth_config.json` 注册环境状态

### 添加新训练方法

1. 如有需要，扩展 `SwiftConfig` 中的枚举类型
2. 在 `SwiftBackend.generate_script()` 中添加对应逻辑
3. 在 `forge/cli_train.py` 中添加 CLI 选项

### 添加新计算后端

1. 在 `forge/training/executor/` 中实现 `ExecutorProtocol`
2. 在训练 CLI 中注册新后端选项

---

## 十一、文件写入权限矩阵

| 文件 | Strategist | Trainer | Data Agent |
|------|:---:|:---:|:---:|
| 自己的 ROLE.md | ✅ | ✅ | ✅ |
| 他人 ROLE.md（对抗区） | ✅ | ❌ | ❌ |
| PLAYBOOK.md | ✅ | 只读 | 只读 |
| experiments/*.yaml | ✅（设计） | ✅（结果） | 只读 |
| synth_config.json | 只读 | 只读 | ✅ |
| knowledge/*.md | ✅ | ✅ | ✅ |

---

*文档更新时间：基于三层架构重构*
