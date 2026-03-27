# Affine-Swarm 工作报告：三层架构重构 + Qwen3-32B Full SFT 训练

> 日期：2026-03-28
> 作者：wangtong10086
> 仓库：https://github.com/wangtong10086/affine-swarm
> 分支：`refactor/three-layer-architecture`

---

## 一、工作概述

本次工作分为两个并行推进的方向：

1. **架构重构**：将 `forge/` 单体代码包重构为三层解耦架构（Foundation → Application → Agent），实现环境、Prompt、训练三者零依赖分离。
2. **训练部署**：在 Targon 8×H200 Rental 容器上成功部署 Qwen3-32B Full SFT 训练，使用 ms-swift + DeepSpeed ZeRO-3，解决了一系列运行时问题。

---

## 二、架构重构

### 2.1 问题分析

原有 `forge/` 是单体 CLI 包，存在严重的耦合问题：

| 耦合点 | 问题描述 |
|--------|---------|
| 环境 ↔ 数据清洗 | `sft.py` 中 6 个环境的 cleaner 混在通用数据管道里 |
| 训练 ↔ 配置 | `training/config.py` 以字符串拼接方式生成完整 Python 训练脚本 |
| Prompt ↔ 环境 | system prompt、tool schema 硬编码在各生成脚本中 |
| 评估 ↔ 环境 | 评估逻辑 hardcode 了各环境的 task 生成和评分 |

### 2.2 目标架构

```
┌─────────────────────────────────────────────────────┐
│  Layer 2: Agent 层 — 自动化编排                       │
│  Strategist / Trainer / DataAgent / EvolutionLoop    │
├─────────────────────────────────────────────────────┤
│  Layer 1: Application 层 — 业务流程                   │
│  DataPipeline / Evaluator / ExperimentTracker        │
├─────────────────────────────────────────────────────┤
│  Layer 0: Foundation 层 — 三者零依赖                  │
│  Environment    │   Prompt Engine   │   Training     │
│  (forge/env/)   │   (forge/prompt/) │   Backend      │
└─────────────────┴───────────────────┴────────────────┘
```

**核心设计原则**：
- Layer 0 各模块之间**零依赖**
- Layer 1 可依赖 Layer 0 任意模块
- Layer 2 可依赖 Layer 0 和 Layer 1

### 2.3 实现内容

#### 新增模块

| 模块 | 文件数 | 代码行数 | 职责 |
|------|--------|---------|------|
| `forge/env/` | 11 | 1,004 | 环境抽象层：EnvProtocol、EnvRegistry、GEM 交互协议、Sandbox 生命周期，以及 GAME/NAVWORLD/SWE/LIVEWEB/LGC 等具体实现 |
| `forge/prompt/` | 5+3模板 | 417 | Prompt 引擎：消息构建器、tool schema 管理、模板系统（Markdown + JSON 模板） |
| `forge/training/` (新文件) | 7 | 472 | 训练后端：TrainBackend 协议、SwiftTrainBackend (ms-swift)、model 管理、executor (Targon/SSH) |
| `forge/pipeline/` | 6 | 349 | 应用层：DataPipeline、Evaluator、ExperimentTracker、数据生成器基类 |
| `forge/agent/` | 6 | 457 | Agent 层：Strategist、Trainer、DataAgent、EvolutionLoop 自动化循环 |
| `tests/` | 6 | 1,386 | 全模块测试覆盖 |

#### 重构的现有模块

| 文件 | 变更 | 说明 |
|------|------|------|
| `forge/training/config.py` | -357行 重写 | 字符串拼接 → `SwiftConfig` YAML 生成 |
| `forge/training/runner.py` | 重构 | 适配新 config/executor 模式 |
| `forge/data/sft.py` | -222行 | 环境清洗逻辑提取到 `forge/env/` |
| `forge/cli_train.py` | 扩展 | 支持 SFT/RLHF、LoRA/Full、DeepSpeed |
| `forge/compute/targon.py` | 扩展 | 支持 Rental 容器、Volume 管理 |
| `forge/deploy.py` | -71行 | 模型操作提取到 `training/model.py` |

**总计**：新增 ~4,250 行代码，删除 ~905 行，净增 ~3,345 行。

### 2.4 Commit 记录

```
c04d1a8 feat(scripts): add check_logs.py for remote training log monitoring
c4c6c2d test: add unit tests for all new modules
3d03482 refactor(cli): update CLI and compute layer for ms-swift backend
9c1d592 refactor(data): update data module for new architecture
4720cc8 feat(agent): add agent layer — automated experiment loop (Layer 2)
1a94a3a feat(pipeline): add application layer — data, eval, experiment pipelines (Layer 1)
1d0d80c refactor(training): restructure training module with backend/executor pattern (Layer 0)
956852e feat(prompt): add prompt engine with template system (Layer 0)
4b0cd78 feat(env): add environment abstraction layer (Layer 0)
00ce4d7 docs(arch): add three-layer architecture design and refactoring plan
```

---

## 三、Qwen3-32B Full SFT 训练部署

### 3.1 训练环境

| 项目 | 规格 |
|------|------|
| 模型 | Qwen/Qwen3-32B (32,762M 参数，100% 可训练) |
| 硬件 | 8× NVIDIA H200 144GB (Targon Rental，$19.2/hr) |
| 框架 | ms-swift 4.0.2 + DeepSpeed ZeRO-3 + PyTorch 2.6.0 |
| 数据 | 40,891 条多环境混合数据，有效 23,764 条 |
| 序列长度 | 32,768 tokens |
| 批大小 | per_device=1, gradient_accumulation=4 (有效 batch=32) |
| 优化器 | AdamW, lr=2e-5, cosine schedule, warmup=3% |
| 精度 | bfloat16 |

### 3.2 问题解决链

训练部署过程中遇到 6 个串联问题，逐一解决：

| # | 问题 | 原因 | 解决方案 |
|---|------|------|---------|
| 1 | HF Datasets schema 不一致 | 52% 样本含 `tool_calls`/`tool_call_id` 字段,pyarrow 无法统一 mixed schema | 将 tool_calls 转换为 Hermes 文本格式 (`<tool_call>`/`<tool_response>` 标签)，统一为 `{role, content}` |
| 2 | `FSDPModule` ImportError | PyTorch 2.5.1 缺少 `FSDPModule`（2.6.0 引入） | 升级 torch 到 2.6.0+cu124 |
| 3 | transformers 5.x 不兼容 | transformers 5.3.0 的 lazy import 机制与 ms-swift 不兼容 | 固定 `transformers<5`（安装 4.57.6） |
| 4 | torchvision 版本冲突 | base image 的 torchvision 0.20.1 与 torch 2.6.0 不兼容 | 升级 torchvision 到 0.21.0+cu124 |
| 5 | ZeRO-2 OOM | 32B 模型全参训练在 ZeRO-2 下每 GPU 保留完整参数（~64GB），优化器步骤内存不足 | 切换到 ZeRO-3（分片模型参数+梯度+优化器状态） |
| 6 | 容器重启 | `pkill -f "swift"` 匹配 PID 1 导致容器被杀 | 改用 nohup + 管道脚本方式启动，避免宽模式 pkill |

### 3.3 训练进展

训练于 2026-03-27T19:08 UTC 稳定启动，早期指标：

| Step | Loss | Grad Norm | Token Acc | GPU Memory | Speed |
|------|------|-----------|-----------|------------|-------|
| 1/743 | 0.955 | 5.49 | 77.3% | 76.3 GiB | 80s/step |
| 5/743 | 0.975 | 2.47 | 76.5% | 93.8 GiB | 62s/step |
| 10/743 | 0.870 | 1.10 | 77.9% | 93.8 GiB | 59s/step |
| 15/743 | 0.708 | 1.39 | 80.2% | 94.3 GiB | 55s/step |

- Loss 下降趋势良好：0.955 → 0.708（前 15 步下降 26%）
- 吞吐稳定在 ~55s/step
- 内存使用 94.3/139.4 GiB（67.7%），留有充足余量
- 预计训练总时长：~11 小时（743 步 × 55s/step）

### 3.4 基础设施要点

- **Targon API v2**：使用 REST API 进行容器生命周期管理（register → deploy → monitor via logs/state/events）
- **Volume 持久化**：300GB Volume (`vol-rfrbe1nc8uk5`) 跨容器保留模型缓存、训练数据和 checkpoints
- **Volume 重建**：容器调度到新节点时通过 `reconstruct-pv-agent` 从备份恢复，300GB 约需 29 分钟
- **SSH 可靠性**：SSH 网关对长时间 Python/CUDA 命令不稳定，需通过管道脚本 (`cat script.sh | ssh ... 'bash'`) 或 nohup 执行

---

## 四、关键收获

### 架构层面
1. **三层分离有效降低复杂度**：环境逻辑不再散落在数据管道中，新增环境只需实现 `EnvProtocol`
2. **模板化 Prompt 管理**：从硬编码提升为可版本化、可测试的模板系统
3. **Backend/Executor 模式**：训练方法（SFT/RLHF）与执行环境（Targon/SSH）正交组合

### 训练层面
1. **ZeRO-3 是 32B Full SFT 的必需**：ZeRO-2 在 8×H200 上 OOM（每 GPU ~18GB 模型参数 + 优化器状态超出 144GB）
2. **依赖链版本控制至关重要**：torch 2.6.0 + transformers<5 + torchvision 0.21.0 是经验证的兼容组合
3. **数据 schema 统一**：HF Datasets 的 pyarrow 后端对混合 schema 零容忍，必须在训练前统一所有字段

---

## 五、后续计划

1. **监控训练完成**：跟踪 743 步训练至完成，检查最终 loss 和 checkpoint 上传
2. **模型评估**：训练完成后在全部环境上运行 eval（GAME、NAVWORLD、LIVEWEB 等）
3. **完善测试覆盖**：为新模块添加集成测试，确保端到端流程可靠性
4. **Agent 层集成**：将 EvolutionLoop 接入实际训练-评估流程，实现半自动实验迭代
