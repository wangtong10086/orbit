# 训练迭代日志

## 迭代 #1 — 首次 GAME 训练

**日期**: 2026-03-11
**目标环境**: GAME（3x 权重，最高优先级）
**基准排行榜**: Block 7720452

### 排行榜基准
| 排名 | UID | 模型 | 权重 | GAME | LGC-v2 | LIVEWEB | NAVWORLD | PRINT | SWE-SYNTH |
|------|-----|------|------|------|--------|---------|----------|-------|-----------|
| 1 | 116 | oliverchang/Affine-95 | 0.510 | 29.94 | 81.20 | 23.58 | 10.42 | 73.71 | 38.00 |
| 2 | 120 | voidai001/affine-new | 0.249 | 47.20 | 89.52 | 25.18 | 5.27 | 78.95 | 31.00 |
| 3 | 45 | Infinite3214/Affine-0305 | 0.123 | 41.42 | 89.20 | 28.63 | 5.05 | 85.86 | 28.00 |

### 数据
- **来源**: DynamoDB affine_sample_results，所有矿工的 GAME 高分样本
- **过滤**: score >= 0.5
- **数量**: 4,528 条 SFT 记录（重新提取后增加）
- **格式**: JSONL（messages chat format）
- **存储**: HuggingFace `nomooko/affine-sft-data/game_sft.jsonl`

### 训练配置
- **模型**: Qwen/Qwen3-32B
- **方法**: QLoRA (4-bit NF4 + LoRA r=16, alpha=32)
- **GPU**: Targon H200 (serverless container)
- **Batch**: 2 × 8 grad accum = effective 16
- **学习率**: 2e-5, warmup 10%
- **Epochs**: 3
- **Checkpoint**: 每 100 步保存，自动上传 HuggingFace

### 执行状态

**尝试 1** — `serv-u-1324508-ds3woo1ppdeo8mmi` (已终止)
- 部署时间: 07:25 UTC
- 镜像: `nvidia/cuda:12.4.0-devel-ubuntu22.04`
- 结果: **失败** — 模型下载卡在 18% (3/17 files)，HF 仓库无 checkpoint 上传
- 终止原因: 浪费 $2.40/hr，训练从未真正开始
- 根因分析: 日志显示 pip 安装成功、训练脚本启动、模型下载开始但停滞。可能是 Qwen3-32B 65GB 下载在 Targon 网络超时或磁盘空间不足。

**尝试 2** — `serv-u-1324508-5vwzpiq1m7gkyn2k` (已终止)
- 部署时间: 07:35 UTC
- 镜像: `pytorch/pytorch:2.5.1-cuda12.4-cudnn9-devel`
- 结果: **失败** — 容器零日志输出
- 终止原因: PyTorch 官方镜像可能有不兼容的 entrypoint 或者 Targon 不支持
- 根因分析: Targon serverless 平台对自定义镜像有限制，不是所有 Docker 镜像都能正常工作。回退到已验证的 CUDA 镜像。
- 教训: **只使用已验证能工作的镜像** (`nvidia/cuda:12.4.0-devel-ubuntu22.04`)

**尝试 3** — `serv-u-1324508-kedpsq3y3zrtmg9q` (已终止)
- 部署时间: 07:38 UTC，终止时间: ~08:28 UTC（运行 50 分钟）
- 镜像: `nvidia/cuda:12.4.0-devel-ubuntu22.04`
- 结果: **失败** — 依赖安装和数据集下载成功，训练脚本启动，模型下载开始后无进展
- 48分钟后仍无 HF checkpoint 上传，日志停在 "Fetching 17 files: 0%"
- 根因分析: Qwen3-32B (65GB) 可能下载超时或磁盘空间不足。tqdm 进度条用 `\r` 导致后续日志不可见。
- 教训: **先用小模型验证流水线，再上大模型**

**尝试 4** — `serv-u-1324508-s7l5ryt479xfhygo` (已终止)
- 模型: Qwen2.5-7B, 镜像: `nvidia/cuda:12.4.0-devel-ubuntu22.04`
- 17 分钟仍在 pip install Python dependencies, 终止
- 根因: 从零 pip install torch ~2GB 太慢

**镜像兼容性测试** — `serv-u-1324508-l29ao88ufrb1wnmp` (已终止)
- `nvcr.io/nvidia/pytorch:24.10-py3` → 零日志，不可用
- `pytorch/pytorch:2.5.1-cuda12.4-cudnn9-devel` → 零日志，不可用（尝试 2）
- 结论: **Targon 只支持 nvidia/cuda 系列基础镜像**

**尝试 5** — `serv-u-1324508-3a84ch4u7so2mnib` (已终止)
- 模型: Qwen2.5-7B, 无健康检查服务器, 30+分钟无 HF 上传
- 根因不明，可能因无 HTTP 健康检查被 Targon 限流

**尝试 6** — `serv-u-1324508-xljqzwjysyy37hzw` (已终止)
- 模型: Qwen2.5-7B, 带健康检查服务器
- 结果: **训练脚本报错** `SFTConfig.__init__() got an unexpected keyword argument 'max_seq_length'`
- 根因: pip install 的 trl 最新版本中 `max_seq_length` 不再是 `SFTConfig` 参数，需放到 `SFTTrainer`
- 修复: 将 `max_seq_length` 从 SFTConfig 移到 SFTTrainer 构造函数
- 教训: **容器内 pip install 安装最新版本库，API 可能与本地开发环境不同**

**尝试 7** — `serv-u-1324508-kunjl402ovf10k1t` (已终止)
- 9 分钟后 Targon 日志缓冲清空无法诊断，无 HF 上传

**尝试 8** — `serv-u-1324508-ki3fz9flaggq31j4` (已终止)
- **日志捕获首次成功！** 退出时上传 training.log 到 HF
- 错误: `SFTTrainer.__init__() got an unexpected keyword argument 'tokenizer'`
- 根因: trl 最新版 API 大改 — `tokenizer` → `processing_class`, `max_seq_length` → `max_length`, `warmup_ratio` deprecated
- 修复: 按最新 trl 文档更新所有 API 调用

**尝试 9** — `serv-u-1324508-te0djedy75dd4794` (已终止)
- API 修复生效（tokenizer→processing_class 通过）
- 新错误: `jinja2.exceptions.UndefinedError: dict object has no element 0`
- 根因: `formatting_func` 在新版 trl 中接收单样本而非 batch，且 conversational 数据集不需要 formatting_func
- 修复: 移除 formatting_func，让 trl 自动处理 messages 格式

**尝试 10** — `serv-u-1324508-wvy7glkyhcfu5nck` (**完成** ✅)
- 模型: Qwen2.5-7B, 1 epoch, 283 步
- **最终 loss=0.188, accuracy=96.4%, 运行 51 分钟**
- 流水线完整验证通过：部署 → 训练 → checkpoint → HF 上传 → 日志查看

---

## 迭代 #1B — Qwen3-32B 正式 GAME 训练

**尝试 11** — `serv-u-1324508-782d1hj887mg2faz` (**部分失败**)
- 模型: Qwen/Qwen3-32B, QLoRA 4-bit, 3 epochs
- 预计步数: 849 (283 × 3)
- 部署时间: ~11:01 UTC, 终止时间: ~21:00 UTC (~10h, ~$24)
- **HF 上传回调在 step 240 后完全失效**
- 最后已知状态: step 200, loss=0.070
- 可用 checkpoint: checkpoint-100, checkpoint-200 (on HF)
- **根因**: `LogUploadCallback(upload_every_n_logs=1)` 每 10 步上传日志，HF API 限流后回调异常未恢复
- **修复**: 将 `upload_every_n_logs` 从 1 改为 5（降低上传频率）
- **教训**: HF API 有上传频率限制，不能每次 on_log 都上传；上传失败后应有重试机制

### 故障经验总结
1. **Targon 只支持 `nvidia/cuda` 系列镜像**，PyTorch/NGC 官方镜像均不可用
2. pip install torch 从零安装约需 15 分钟，这是不可避免的开销
3. **Qwen3-32B step 100 可能需要 80-130 分钟**，之前尝试 3 可能过早终止
4. **Targon 日志 API 缓冲区极小**，只保留最近几行，不可靠
5. **每个容器 $2.40/hr**，必须快速诊断失败并释放
6. **tqdm 进度条用 `\r` 覆盖行**，在 SSE 日志中不可见

---

## 数据模块开发

**日期**: 2026-03-11

### 全环境数据分析

| 环境 | 总样本 | 平均分 | 高质量(>=0.7, <=16K) | 备注 |
|------|--------|--------|---------------------|------|
| LGC-v2 | 21,757 | 0.669 | 3,353 | 子任务：Dyck括号、数学、运算符、密码算术、数独、布尔 |
| PRINT | 17,689 | 0.734 | 2,899 | 单轮Q&A，预测程序输出 |
| GAME | 12,984 | 0.360 | 561 | 多轮对弈，assistant回复常为单数字 |
| SWE-SYNTH | 11,594 | 0.335 | 437 (<=32K) | 多轮代码修复，大部分样本>16K |
| LIVEWEB | 15,844 | 0.172 | 3 | 几乎无可用数据 |
| NAVWORLD | 9,867 | 0.060 | N/A | 工具调用格式已更新，跳过 |

### 环境特定清洗器

- **GAME**: 验证完整对弈（system prompt + 交替轮次 + assistant结尾）
- **LGC-v2**: 验证think块完整性、按任务类型检查格式要求
- **PRINT**: 验证think块闭合 + 有实际答案输出
- **SWE-SYNTH**: 验证system prompt + 多轮结构 + 实质性代码内容

### 关键发现
1. LGC-v2 初始清洗器要求所有样本包含 python 代码块，但实际只有 ~20% 任务需要 → 修正后恢复 3,353 条（从 646）
2. SWE-SYNTH 放宽到 32K chars 后恢复 437 条（从 26）
3. 混合数据集 7,250 条，99% 满分，覆盖 4 个环境

### 新增 CLI 命令
- `forge data analyze <path>` — 分析数据集质量
- `forge data extract-all` — 批量提取所有环境
- `forge data merge` — 合并多环境数据集
- `forge data extract` — 新增 `--max-chars` 选项

---

## 快速实验 #1 — 从 Top 模型 QLoRA SFT

**日期**: 2026-03-11
**容器**: `serv-u-1324508-11avuf2u6skigj9r` (已终止)

### 实验设计
- 基础模型: #2 UID 120 (`voidai001/affine-new`, GAME 47%)
- 数据: 混合 7250 条 (GAME+LGC-v2+PRINT+SWE-SYNTH)
- 方法: QLoRA, LR=1e-5, 1 epoch
- 目标: 验证从 top 模型微调是否比从 base 训练更好

### 结果: **失败**
| Step | Loss |
|------|------|
| 5 | 0.640 |
| 10 | 0.913 ⬆ |
| 15 | 0.860 |
| 20 | 0.768 |
| 25 | 0.821 |
| 30 | 0.704 |
| 35 | 0.813 |
| 40 | 0.922 ⬆ |

Loss 剧烈震荡不收敛，40 步后终止。

### 对比
- 从 base Qwen3-32B: step 5 loss=0.612 → step 170 loss=0.071（稳定下降）
- 从 top #2 模型: step 5 loss=0.640 → step 40 loss=0.922（震荡发散）

### 结论
- Top 模型已被深度调优，QLoRA 无法在其上稳定学习
- **从 base Qwen3-32B 训练是正确路径**
- 如果要利用 top 模型，可能需要：full fine-tune 或更低 LR (1e-6) 或更长 warmup

### Bug 发现
- `runner.py` 第 91 行总是覆盖 `tc.hf_backup_repo`，导致实验日志写到主训练 repo
- 已修复：只在 `tc.hf_backup_repo` 为空时才使用默认值

---

## 策略分析 — 多环境训练的必要性

**日期**: 2026-03-11

### 核心发现

1. **几何平均惩罚机制**：排行榜用几何平均评分所有 6 个环境，任何短板都会严重拖垮总分
2. **#1 靠均衡取胜**：UID 116 权重是 #2 的两倍，不是因为某项极强，而是没有短板
3. **GAME-only SFT 风险高**：
   - GAME 的 assistant 回复常为单数字，与其他环境的长文生成风格迥异
   - 3 epoch 训练 4528 条 GAME 数据，模型会过度拟合 GAME 分布
   - QLoRA 只更新 0.5% 参数，但长期训练仍可能导致灾难性遗忘
4. **NAVWORLD/LIVEWEB 人人弱**：所有 top 矿工都很低（5-10/23-29），差异在其他环境

### 混合训练方案

| 环境 | 原始 | 混合后 | 策略 |
|------|------|--------|------|
| GAME | 561 | 1,683 | 3x 上采样（最高 ROI） |
| LGC-v2 | 3,353 | 1,500 | 下采样 |
| PRINT | 2,899 | 1,500 | 下采样 |
| SWE-SYNTH | 437 | 437 | 全量 |
| **总计** | — | **5,120** | — |

### 混合训练配置（vs GAME-only）

| 参数 | GAME-only | 混合训练 | 理由 |
|------|-----------|---------|------|
| LR | 2e-5 | 1e-5 | 降低以保护通用能力 |
| Epochs | 3 | 2 | 避免小数据集过拟合 |
| LoRA rank | 16 | 32 | 多环境需更大容量 |
| Max seq len | 4096 | 8192 | SWE-SYNTH 需要 |
| Batch size | 2 | 1 | 适应更长序列 |
| Grad accum | 8 | 16 | 保持 effective=16 |

### 准备工作
- [x] 平衡混合数据集 `mixed_balanced_sft.jsonl` (5120 条) 已创建并上传 HF
- [x] HF repo `nomooko/affine-qwen3-32b-mixed-lora` 已创建
- [x] CLI `train launch` 命令已实现，支持自定义训练参数
- [ ] GAME-only 训练完成后启动混合训练

### 启动命令
```bash
python3 -m forge train launch mixed_balanced_sft.jsonl \
  --hf-repo nomooko/affine-qwen3-32b-mixed-lora \
  --lr 1e-5 --epochs 2 --lora-r 32 \
  --max-seq-len 8192 --batch-size 1 --grad-accum 16
```

---

## NAVWORLD 合成数据生成

**日期**: 2026-03-11

### 环境分析
- NAVWORLD (QQR) 是中文旅行规划 Agent 评测
- 使用高德地图 API (POI/天气/路线) + Mock 交通数据 (航班/火车)
- 评分: 50 分代码评分 (info consistency + completeness) + 50 分 LLM 语义评分
- **标准工具调用格式**: LLM 通过 OpenAI function calling 调用工具
- **Conversation 存储**: 工具调用转为文本格式 ("调用工具: name({args})")

### 排行榜 NAVWORLD 现状
- #1 UID 116: 10.42 (人人都弱，这是 #1 领先的关键差异化点)
- #2 UID 120: 5.27
- #3 UID 45: 5.05

### 数据生成方案
- **编排式生成**: 程序化规划工具调用序列 → 真实 AMap API 获取数据 → 强模型生成方案
- **工具覆盖**: 每个样本保证调用 4-5 种工具 (poi_search/weather/direction/around_search/flights/trains)
- **LLM 模型**: DeepSeek-V3-0324 via Chutes API
- **多轮对话**: 3-4 轮工具调用 + 最终完整方案，9-11 条消息

### 生成进度
- [x] 生成器 `forge/data/navworld_gen.py` 完成
- [x] CLI 命令 `forge data navworld-gen` 可用
- [x] 测试 3 条通过验证
- [x] 批量生成 161 条合成数据（3 批并行，DeepSeek-V3-0324 via Chutes）
- [x] 合并验证：161 合成 + 79 真实 = 240 条 NAVWORLD
- [x] 上传到 HF `nomooko/affine-sft-data/navworld_synthetic_all.jsonl`
- [x] 纳入增强混合数据集

### 文件
- 生成器: `forge/data/navworld_gen.py`
- 合成数据: `data/navworld_synthetic_all.jsonl` (161 条)
- 真实数据: `data/navworld_real_sft.jsonl` (79 条)

---

## 迭代 #2 — 增强混合训练（含 NAVWORLD）

**日期**: 2026-03-11
**目标**: 全环境均衡训练，重点补齐 NAVWORLD 短板

### 数据集: enhanced_mixed_sft.jsonl (5600 条)

| 环境 | 原始 | 混合后 | 策略 |
|------|------|--------|------|
| GAME | 561 | 1,683 | 3x 上采样（最高 ROI） |
| LGC-v2 | 3,353 | 1,500 | 下采样 |
| PRINT | 2,899 | 1,500 | 下采样 |
| SWE-SYNTH | 437 | 437 | 全量 |
| NAVWORLD | 240 | 480 | 2x 上采样（合成161+真实79） |
| **总计** | — | **5,600** | — |

### 训练配置
- **模型**: Qwen/Qwen3-32B（从 base 训练）
- **方法**: QLoRA (4-bit NF4 + LoRA r=32, alpha=64)
- **GPU**: Targon H200 (serverless container)
- **Batch**: 1 × 16 grad accum = effective 16
- **学习率**: 1e-5, warmup 10%
- **Epochs**: 2
- **Max seq len**: 8192
- **Checkpoint**: 每 100 步保存，自动上传 HuggingFace
- **HF Repo**: `nomooko/affine-qwen3-32b-mixed-lora`

### 执行状态

**尝试 1** — `serv-u-1324508-j0mvacby3xzbid18` (**HF 上传失败**)
- 部署时间: ~16:30 UTC, 终止: ~23:00 UTC (~6.5h, ~$16)
- 训练进展: step 310/700, loss=0.454, acc=83.1%
- HF 上传在 step 310 后完全失效（同 GAME 训练的问题）
- 可用 checkpoint: 100, 200, 300
- 训练可能已完成但最终模型无法获取

**根因分析**: HF 上传回调缓存了 HfApi 实例，连接池/认证状态在多次上传后腐化，
后续所有上传静默失败。`on_train_end` 回调也受影响。

**修复** (已应用):
1. 每次上传创建新 HfApi 实例（不缓存）
2. 3 次重试 + 指数退避（10s, 20s, 30s）
3. 降低日志上传频率为每 50 步

**尝试 2** — `serv-u-1324508-emathe3c8bz7kdeg` (运行中)
- 部署时间: ~23:30 UTC (2026-03-11)
- 使用修复后的 HF 上传回调（新 HfApi 实例 + 重试）
- **修复无效**: HF 上传在 step 200 后再次停止
- 已知上传数据: step 200, loss=0.481, acc=82.6%
- 可用 checkpoint: 100 (新 run), 200 (新 run), 300 (旧 run)
- 预计步数: ~700, 每步 ~45s, 总时间 ~8.75h
- 预计完成: ~08:15 UTC (2026-03-12)

**训练曲线 (尝试 2, 截至 step 200)**:
| Step | Loss | Acc | LR |
|------|------|-----|-----|
| 10 | 0.741 | 76.1% | 2.6e-6 |
| 50 | 0.672 | 76.9% | 9.8e-6 |
| 100 | 0.630 | 78.2% | 9.0e-6 |
| 150 | 0.536 | 80.7% | 8.6e-6 |
| 200 | 0.481 | 82.6% | 8.1e-6 |

**HF 上传问题深层分析**:
- 新建 HfApi + 3次重试仍然失败
- 可能原因: Targon 容器网络限制、HF API 全局限流、training.log 文件增长导致超时
- 仍寄希望于 `on_train_end` 最终上传（上传 final 模型文件夹）

---

## HF 上传回调 Bug 总结

**影响**: 3 次训练运行（GAME-only, Mixed v1, Mixed v2）都在 ~step 200-300 后丢失 HF 可见性
**成本**: GAME ~$24 + Mixed v1 ~$16 + Mixed v2 ~$20 = ~$60，其中大部分训练成果无法验证

**已尝试修复**:
1. ❌ 降低上传频率 (every 50 steps instead of 10)
2. ❌ 新建 HfApi 实例（不缓存）
3. ❌ 3次重试 + 指数退避

**待尝试方案**:
1. 不上传 training.log（只上传小 JSON 状态文件）
2. 使用 subprocess 调用 `huggingface-cli upload` 代替 Python API
3. 用后台线程做上传，避免阻塞训练进程
4. 完全不依赖中间上传，只在训练结束后做一次大上传

---

## 循环 — 2026-03-12 08:10 UTC

### 排行榜（Block 7727853）
| 排名 | UID | GAME | LGC-v2 | LIVEWEB | NAVWORLD | PRINT | SWE-SYNTH |
|------|-----|------|--------|---------|----------|-------|-----------|
| 1 | 179 | 45.76 | 92.92 | 25.42 | 15.85 | 81.08 | 29.00 |
| 2 | 45 | 43.93 | 91.60 | 26.71 | 12.02 | 84.66 | 27.00 |
| 3 | 142 | 39.47 | 80.40 | 16.87 | 14.16 | 73.02 | 51.00 |
| 4 | 120 | **46.75** | **95.56** | 24.60 | **7.56** | 80.63 | **34.00** |

### 分析
- **我们 #4**（从 #2 掉落），权重 0.059
- **致命短板**: NAVWORLD 7.56 vs #1 的 15.85（-8.29 差距）
- **领先环境**: GAME +0.99, LGC-v2 +2.64, SWE-SYNTH +5.00
- **几何平均瓶颈**: NAVWORLD 一个环境拖垮整体排名

### 行动
1. **终止容器** `emathe3c8bz7kdeg`（训练完成但 HF 上传 step 200 后失效，空跑 6 小时）
2. **修复 HF 上传 bug**: 改用 subprocess 隔离上传（写 JSON 任务文件 → 独立 Python 进程执行上传）
   - 根因：训练进程内的 HfApi 在长时间运行后状态腐化（连接池/内存/CUDA 干扰）
   - 方案：`_subprocess_hf_upload()` + `_HF_UPLOAD_WORKER_CODE` + JSON 任务通信
   - 每次上传 fork 新进程，完全隔离，300s 超时
3. **可用模型**: checkpoint-100/200/300 在 HF，300 是最佳（loss 0.454, accuracy 84%）

### 下一步
- 规划下一轮训练，重点提升 NAVWORLD
- 向数据 session 下发指令：加大 NAVWORLD 合成数据量和质量
- 新训练使用 subprocess 上传方案验证修复

---

## 迭代 #3 — Mixed v3 训练（NAVWORLD + LIVEWEB 加强）

**日期**: 2026-03-12
**目标**: 缩小 NAVWORLD 差距（7.56→15+），补强 LIVEWEB
**容器**: `serv-u-1324508-z59024vtap3zysl7`
**模型 HF**: `nomooko/affine-qwen3-32b-mixed-v3`

### 数据重大更新
DynamoDB 数据量大幅增长：
- **NAVWORLD**: 79 → **248** 条（score≥0.3）
- **LIVEWEB**: 3 → **1163** 条（score≥0.5 过滤后 844 条）
- **SWE-SYNTH**: 437 → 412 条（score≥0.5, ≤32K chars）

### 训练数据配比（mixed_v3_sft.jsonl，12422 条）
| 环境 | 原始 | 加权 | 占比 | 排行榜状况 |
|------|------|------|------|-----------|
| GAME | 561 | 1122 (2x) | 9.0% | 领先+0.99 |
| LGC-v2 | 3353 | 3000 (1x cap) | 24.2% | 领先+2.64 |
| PRINT | 2899 | 2899 (1x) | 23.3% | 落后-0.45 |
| SWE-SYNTH | 412 | 824 (2x) | 6.6% | 领先+5.00 |
| NAVWORLD real | 248 | 1240 (5x) | 10.0% | **短板-8.29** |
| NAVWORLD synth | 161 | 805 (5x) | 6.5% | 合成数据 |
| LIVEWEB | 844 | 2532 (3x) | 20.4% | 落后-0.82 |

### 训练超参数
- 模型: Qwen/Qwen3-32B QLoRA (4-bit NF4)
- lr=1e-5, epochs=2, LoRA r=32/alpha=64
- max_len=8192, batch=1, grad_accum=16
- HF 上传: **subprocess 隔离**（新修复 _HF_UPLOAD_WORKER_CODE）

### 关键改进
1. **HF 上传 bug 修复**: 每次上传 fork 独立 Python 进程，通过 JSON 文件传参，300s 超时
2. **训练脚本预上传**: 脚本上传到 HF dataset repo，容器下载执行（避免 Targon args 过大）
3. **NAVWORLD 5x 加权**: 从 6.5% 提升到 16.5% 占比
4. **LIVEWEB 首次纳入**: 844 条高分数据（score≥0.5），3x 加权

### 预期
- 12422 样本 / 16 有效批次 = ~776 步/epoch × 2 = ~1553 步
- 每步 ~15s → 约 6.5 小时

### 部署历史
1. **直接 SDK 调用** (08:30 UTC): 容器 `z59024vtap3zysl7`，50 分钟无上传，终止
   - 原因：绕过 runner.py 手动构建 args，转义序列问题导致脚本下载失败
2. **CLI 修复后** (09:30 UTC): 容器 `sc0k61mpx8rbm3k2`，正常部署
   - 修复了 CLI dataset_file 解析 bug（repo:file 格式导致容器名含非法字符）
   - 训练脚本预上传 HF，容器下载执行

### Bug 修复记录
- `forge/cli.py`: 解析 `repo:file` 格式（如 `nomooko/affine-sft-data:mixed_v3_sft.jsonl`）
- `forge/training/runner.py`: 脚本预上传 HF，避免 args 过大
- `forge/training/config.py`: HF 上传改用 subprocess 隔离

### 实际执行结果 (2026-03-12 更新)

**HF subprocess 上传修复验证成功!**

容器 `sc0k61mpx8rbm3k2` 的 HF repo `nomooko/affine-qwen3-32b-mixed-lora` 检查结果：
- ✅ checkpoint-100 已上传
- ✅ checkpoint-200 已上传
- ✅ checkpoint-300 已上传
- ✅ training_log.json 已上传（包含完整 loss 曲线至 step 200）
- ✅ training.log 已上传

**训练速度修正**: 实际每步 ~45-52s（非估计的 15s），因 max_seq_len=8192 序列很长。

**Loss 曲线 (checkpoint-300/trainer_state.json)**:
| Step | Loss | Token Acc | LR |
|------|------|-----------|-----|
| 10 | 0.741 | 76.1% | 2.6e-6 |
| 50 | 0.672 | 76.9% | 9.8e-6 |
| 100 | 0.630 | 78.2% | 9.0e-6 |
| 150 | 0.511 | 81.0% | 8.3e-6 |
| 200 | 0.481 | 82.6% | 7.5e-6 |
| 250 | 0.451 | — | — |
| 300 | 0.454 | — | — |

Loss 在 step 250 后趋于平稳 (~0.45)。训练可能在 step 300-400 达到最优。

**容器终止统计 (本 session)**:
| 容器 | 用途 | 运行时间 | 结果 |
|------|------|---------|------|
| emathe3c8bz7kdeg | mixed v2 | ~6h | 训练完成但 HF 上传失效，step 200 后无可见性 |
| z59024vtap3zysl7 | mixed v3 直接SDK | ~50min | 脚本下载失败 |
| sc0k61mpx8rbm3k2 | mixed v3 CLI | ~3h+ | **checkpoint-300 成功上传** ✅ |
| 2vhgsxlujlcp0b54 | 100样本测试 | ~15min | save_steps=100 设置错误 |
| ygxy2aq4yeymp2z3 | 500样本测试 | ~30min | 过早终止（实际需 46min 才到首次上传） |
| pd68u3ithhuue4vu | 诊断 | ~5min | 放弃 |

**本 session 总成本**: ~$26 ($2.40/hr × ~11h 总容器时间)

---

## 循环 — 2026-03-12 ~19:00 UTC

### 排行榜 (Block 7729709)

| 排名 | UID | 权重 | GAME | LGC-v2 | LIVEWEB | NAVWORLD | PRINT | SWE-SYNTH |
|------|-----|------|------|--------|---------|----------|-------|-----------|
| 1 | 179 | 0.509 | 46.1 | 92.6 | 25.5 | 16.8 | 82.3 | 25.0 |
| 2 | 45 | 0.253 | 45.8 | 90.8 | 26.3 | 15.7 | 83.9 | 25.0 |
| 3 | 142 | 0.124 | 40.6 | 79.6 | 16.5 | 18.6 | 72.3 | 44.0 |
| 4 | 120 | 0.061 | 47.2 | 95.2 | 24.3 | 10.5 | 80.9 | 30.0 |
| 5 | 71 | 0.030 | 42.0 | 83.2 | 17.7 | 16.6 | 67.0 | 38.0 |

### 关键洞察

1. **Subprocess HF 上传已验证**: checkpoint-100/200/300 全部成功上传，训练流水线可靠
2. **训练速度**: max_seq_len=8192 → ~50s/step，完整 1554 步训练需 ~23h ($55)
3. **Loss 收敛**: step 250-300 后 loss 趋平 (~0.45)，更长训练可能无显著改善
4. **无评测能力**: 本地无 GPU/Docker 权限，无法运行 affinetes 评测

### 排行榜战略分析

**NAVWORLD 仍是全局差异化关键**:
- 全员弱 (10-18%)，我们 UID 120 = 10.5%（最差之一）
- 462 条合成+真实数据已准备，5x 加权纳入训练

**SWE-SYNTH 差距扩大**:
- #3 UID 142 = 44%，我们 = 30%
- 需要更多高分 SWE-SYNTH 数据或专项训练

**LIVEWEB 有机会**:
- #2 UID 45 = 26.3% 领先，844 条数据已有
- 首次纳入训练，效果待评测

### 阻塞与待解决

1. **评测**: 需要 Docker 权限或 Targon 部署 vLLM 来评测 checkpoint-300
2. **训练速度**: 考虑降低 max_seq_len 到 4096（大部分样本可能不需要 8192）
3. **checkpoint-300 训练未完成**: 300/700 步（~43%），但 loss 已趋平
4. **成本控制**: 避免盲目长时间训练，需要评测反馈才能指导下一步

---

## 循环 — 2026-03-12 ~20:30 UTC — 数据质量深度审计

### 排行榜 (Block 7730311)

| 排名 | UID | 权重 | GAME | LGC-v2 | LIVEWEB | NAVWORLD | PRINT | SWE-SYNTH |
|------|-----|------|------|--------|---------|----------|-------|-----------|
| 1 | 45 | 0.508 | 45.3 | 91.2 | 26.6 | 16.2 | 84.4 | 22.2 |
| 2 | 142 | 0.253 | 40.8 | 78.8 | 16.4 | 19.5 | 72.1 | 44.0 |
| 3 | 120(我们) | 0.125 | **47.6** | **95.2** | 24.2 | 10.6 | 80.9 | 32.3 |
| * | 248 | 0.000 | 62.3 | 93.3 | 21.8 | **33.7** | 73.3 | 27.3 |

**变化**: 我们从 #4 升 #3，Foremost01 掉出 Top 10。RLStepone NAVWORLD 33.7% 是巨大威胁。

### 数据质量审计结果（三项严重问题）

#### 问题 1: NAVWORLD 合成数据格式完全错误 🔴
- 431 条合成数据使用文本格式 ("调用工具: xxx") 而非 Qwen3 `<tool_call>` 格式
- 模型训练后输出纯文本而非标准工具调用，评测环境无法解析
- **已修复**: 转换为标准 tool_calls + tool 角色格式，432 条验证通过

#### 问题 2: SWE-SYNTH 尾部消息角色错误 🔴
- 444 条数据最后一条消息全是 user 角色（diff 内容）
- 模型学习预测 user 输出而非 assistant 回复
- **已修复**: 删除尾部 user 消息

#### 问题 3: LIVEWEB 数据全部超长无效 🔴
- 844 条数据中位数 145K 字符（~36K tokens）
- max_seq_len=8192 下 0 条可用（全部被截断到对话开头）
- 2532 条训练数据（20.4%占比）完全是噪音
- **已修复**: 从训练集移除

#### 其他问题
- GAME: 38 条重复 → 已去重
- GAME: assistant 回复全是单数字（1-3 字符），无推理过程 → 环境特性，暂不处理

### 训练超参优化（基于前沿论文研究）

| 参数 | v3 (旧) | v4 (新) | 依据 |
|------|---------|---------|------|
| learning_rate | 1e-5 | **1e-4** | QLoRA 标准范围，旧值低 10x |
| lora_r | 32 | **64** | 多任务需更大容量 |
| epochs | 2 | **1** | 防过拟合，SFT 1-2 epoch 足够 |
| warmup | 10% | **3%** | 标准推荐 |
| max_grad_norm | 1.0 | **0.3** | QLoRA 论文推荐 |
| packing | False | **True** | 短样本效率提升 2-3x |
| max_seq_len | 8192 | **4096** | LIVEWEB 已移除，其他环境够用 |

### Mixed v4 数据集 (6000 样本)

| 环境 | 样本数 | 占比 | 关键改进 |
|------|--------|------|---------|
| GAME | 1200 | 20% | 去重 |
| NAVWORLD | 1200 | 20% | **正确 tool_call 格式** |
| PRINT | 1560 | 26% | — |
| LGC-v2 | 1320 | 22% | — |
| SWE-SYNTH | 720 | 12% | **修复尾部 user** |

预估: ~250 步, ~2h, ~$5

### 竞争对手分析
- 所有 Top 模型: Qwen3-32B 全量合并上传
- RLStepone: 暗示使用 RL 方法，NAVWORLD 33.7% 远超 SFT 方案
- 训练细节不公开，竞争力在数据质量

### 下一步
1. 用户确认后上传 mixed_v4 + 启动训练
2. 训练完成后需解决评测问题（Docker/Targon vLLM）
3. 关注 RLStepone 是否样本数达标

---

## 循环 — 2026-03-12 ~21:00 UTC — Mixed v4 训练启动

### 排行榜 (Block 7730361) — 我们 #1！

| 排名 | UID | 权重 | GAME | LGC-v2 | LIVEWEB | NAVWORLD | PRINT | SWE-SYNTH |
|------|-----|------|------|--------|---------|----------|-------|-----------|
| **1** | **120(我们)** | **0.507** | **47.6** | **95.2** | 24.2 | 10.8 | 80.9 | 32.3 |
| 2 | 45 | 0.253 | 45.3 | 91.2 | 26.6 | 16.2 | 84.4 | 20.6 |
| 3 | 142 | 0.126 | 40.8 | 78.8 | 16.4 | 19.5 | 72.1 | 41.8 |

### 行动: Mixed v4 训练启动

**容器**: `serv-u-1324508-f57pyto88sd7ef95` (2x H200-M, $4.80/hr)

**训练配置 (v4)**:
- 数据: mixed_v4_sft.jsonl (6000 样本, 无 LIVEWEB)
- lr=1e-4, LoRA r=64/alpha=128, 1 epoch
- max_seq_len=4096, batch=2, grad_accum=4, packing=True
- max_grad_norm=0.3, warmup=3%
- 多卡: accelerate launch DDP (2x H200)
- HF backup: nomooko/affine-qwen3-32b-v4

**关键改进 (vs v3)**:
1. NAVWORLD: 文本格式→标准 tool_call 格式
2. SWE-SYNTH: 删除错误的尾部 user 消息
3. LIVEWEB: 移除（全部超长无效）
4. lr: 1e-5→1e-4 (QLoRA 标准范围)
5. packing: 短样本打包，效率 2-3x
6. 多卡 DDP: 2x H200 数据并行

**预估**: ~375 步 (6000/16), ~3-4h (含 setup), ~$15-20

---

## 循环监控 — 2026-03-12 16:31 UTC

### 排行榜 (Block 7730361)

| 排名 | UID | 模型 | 权重 | GAME | NAVWORLD | SWE-SYNTH |
|------|-----|------|------|------|----------|-----------|
| 1 | 120 | voidai001/affine-new | 0.507 | 47.6 | 10.8 | 32.3 |
| 2 | 45 | Infinite3214/Affine-0305 | 0.253 | 45.3 | 16.2 | 20.6 |
| 3 | 142 | AnastasiaFantasy | 0.126 | 40.8 | 19.5 | 41.8 |
| 8 | 242 | RLStepone/h2 (19样本) | 0.000 | 53.6 | 24.5 | 0.0 |
| 10 | 248 | RLStepone/h3 (18样本) | 0.000 | **64.4** | **33.7** | 27.3 |

**关键发现**:
- RLStepone-h3 GAME 64.4 + NAVWORLD 33.7，远超所有人，正在爬升（仅 18 样本）
- NAVWORLD 仍是全局最弱环境，差异化机会最大
- 我们不在排行榜（训练中）

### 训练状态

- 容器 `f57pyto88sd7ef95` 存活（HTTP 404），HF v4 仓库空
- 可能还在 setup（下载模型）或训练未达 step 100
- 暂不终止，下轮再检查

### 数据 Session

- status=idle，已下发 4 个任务到 data_synth.md
- 任务 1: NAVWORLD tool_call 格式生成 (300+)
- 任务 2: DynamoDB 定期刷新
- 任务 3: GAME 推理样本调查
- 任务 4: MemoryGym 预生成

### 下一步

1. 10 分钟后再查 HF v4 仓库，确认训练进度
2. 如果仍无上传 → 容器可能有问题，考虑终止重启
3. 训练完成后 → 需要解决评测基础设施问题（问用户）

---

## DPO Pipeline 开发 — 2026-03-12 17:00 UTC

### 背景

用户建议尝试 RL 方法。分析后选择 **DPO (Direct Preference Optimization)**：
- 离线方法，不需要在线推理，QLoRA 兼容
- DynamoDB 中同一 task_id 有多个 miner 的不同分数响应 → 天然 preference pairs
- trl `DPOTrainer` 稳定版，原生支持 tool_calls
- 训练路径：SFT checkpoint → DPO 对齐

### 实现内容

1. **`forge/data/sft.py`**: 新增 `export_dpo_data()` — 按 task_id 分组，高分=chosen，低分=rejected
2. **`forge/training/config.py`**: 新增 `to_dpo_script()` — 生成 DPO 训练 Python 脚本
3. **`forge/cli.py`**: 新增 `data extract-dpo` 和 `train dpo-launch` 命令
4. **`forge/training/runner.py`**: 改进容器启动脚本，增加 apt-get 重试和 pip bootstrap fallback

### DPO 数据提取结果

| 环境 | Preference Pairs | 平均分差 |
|------|-----------------|---------|
| GAME | 589 | 0.746 |
| LGC-v2 | 800 (capped) | 1.000 |
| NAVWORLD | 241 | 0.443 |
| PRINT | 800 (capped) | 1.000 |
| SWE-SYNTH | 258 | 1.000 |
| **合计** | **2688** | — |

混合 DPO 数据集 `mixed_dpo.jsonl` (79.5MB) 已上传 HF `nomooko/affine-sft-data`。

### v4 训练失败诊断

容器 `f57pyto88sd7ef95` 日志显示：
- Targon 网络完全不通（所有 apt 源 Connection refused）
- `apt-get install python3-pip` 失败 → `python3` 不可用 → 训练未开始
- 容器已终止，避免继续空烧 $4.80/hr

**修复**: runner.py 启动脚本增加 apt-get 重试 (3次) + pip bootstrap fallback。

### DPO 训练计划

**策略**: SFT → DPO 两阶段训练
1. 先完成 SFT 训练（mixed_v4_sft.jsonl, 6000 样本）获得基础能力
2. 在 SFT checkpoint 上跑 DPO（mixed_dpo.jsonl, 2688 pairs）进行偏好对齐

**DPO 超参**:
- beta=0.1, lr=5e-6, batch=1, grad_accum=8
- LoRA r=64, alpha=128
- max_length=4096, max_prompt_length=2048
- 1 epoch

**CLI 命令**:
```bash
# 提取 DPO 数据
python3 -m forge data extract-dpo GAME --min-chosen-score 0.5 --min-score-gap 0.15

# 启动 DPO 训练
python3 -m forge train dpo-launch mixed_dpo.jsonl \
  --hf-repo nomooko/affine-qwen3-32b-dpo \
  --sft-adapter nomooko/affine-qwen3-32b-v4 \
  --gpu H200
```

### 下一步

1. 重新启动 SFT 训练（需要先有 SFT checkpoint）
2. SFT 完成后，在其上跑 DPO
3. 或者：直接从 base 模型跑 DPO（跳过 SFT），对比效果

---

## Targon 网络故障 — 2026-03-12 17:10 UTC

### 排行榜变化

AnastasiaFantasy 升至 #1（0.507），voidai 降至 #3（0.126）。关键：Anastasia 靠 NAVWORLD 19.8 + SWE-SYNTH 42.0 均衡取胜。

### Targon 出站网络完全瘫痪

连续 3 台容器全部因网络不可用而失败：
1. `f57pyto88sd7ef95` (H200-M) — apt Connection refused, 终止
2. `s97xo4chiolo6hcd` (H200) — 同样 apt 失败, 终止
3. `795bkdwgpx0vd80k` (H200, PyTorch 镜像) — 零日志输出, 终止
4. `z1sibtgx5es0x87p` (H200, CUDA 镜像 + 重试) — apt 失败 5 次, 终止

**根因**: Targon serverless 容器出站网络连接被拒绝（HTTP/HTTPS 均不通）。无法安装 python3-pip、下载 HF 模型、或运行任何需要网络的操作。

**尝试过的方案**:
- CUDA 镜像 + apt-get 重试 → 网络不通
- PyTorch 镜像（自带 python/pip/torch）→ Targon 不支持（零日志）
- pip bootstrap via curl → 容器内无 curl

**可能的解决方案**:
1. 等待 Targon 修复网络（之前的训练成功过，说明不是永久问题）
2. 构建自定义 Docker 镜像（预装所有依赖），推到 Docker Hub
3. 使用其他 GPU 提供商（SSH 后端）
4. 用户提供有 GPU 的机器

**成本损失**: ~$5（4 台容器各运行 10-30 分钟）

---

## Loop 迭代 — 2026-03-12 ~17:40 UTC

**排行榜**: #1 UID 142 (weight 0.507), 我们未上榜
- 新选手 RLStepone (UID 242/248) 样本少但分数高: GAME 47-51, NAVWORLD 22-28, PRINT 75-94
- NAVWORLD 全场最弱 (7-28)，差异化机会最大

**训练状态**: 完全阻塞
- Targon 出站网络持续瘫痪（~2h+ 确认）
- 本轮又尝试 3 个容器: H200 CUDA + 诊断, H200-M CUDA, H200 网络测试
- 全部失败: `Connection refused` on port 80/443, 无法 apt-get/pip/curl
- PyTorch 镜像: Targon 不支持（零日志 + logs API 500）
- 累计成本: ~$3 额外

**代码改进** (本轮完成):
1. 修复 bash `&` bug: `(...&)` 子shell隔离，确保只后台化 http server
2. 添加诊断输出: which python3/pip/curl/wget + OS 版本 + apt-get 全量错误
3. 发现 `| tail` 掩盖 apt-get 退出码（非阻塞 bug，待修）

**数据状态**: 就绪，无需行动
- SFT: 5600 条 (enhanced_mixed_sft.jsonl) 已上传 HF
- DPO: 2688 对 (mixed_dpo.jsonl) 已上传 HF
- DynamoDB 刷新: 2.7h 前，不需要

**决策**: 等待 Targon 恢复，不再浪费资源重试。训练计划不变:
1. SFT (enhanced_mixed_sft.jsonl, 5600条) → nomooko/affine-qwen3-32b-v4
2. DPO (mixed_dpo.jsonl, 2688对) → 在 SFT checkpoint 上微调

---

## Loop 迭代 — 2026-03-12 ~18:00 UTC

**排行榜**: 无变化。#1 UID 142 (0.507)

**Targon 网络深度诊断**:
- 用 bash `/dev/tcp` 测试了 4 个 HTTPS 目标: huggingface.co, github.com, google.com, pypi.org
- **全部 CLOSED / Network unreachable** — IPv4 Connection refused, IPv6 Network unreachable
- 结论: Targon 容器**出站网络完全隔离**，不是特定端口/目标的问题
- 之前的训练能成功说明这是 Targon 基础设施故障，非正常状态
- 累计测试成本: ~$2 额外

**行动**: 无法训练。需要用户介入:
1. 联系 Targon 支持确认网络状态
2. 或提供替代 GPU 资源（SSH 机器）
3. 或使用其他 GPU 云服务商

---

## Loop 迭代 — 2026-03-12 ~18:20 UTC

**排行榜变化**: **新 #1!** UID 179 (Foremost01/affine-n) 夺冠 (weight 0.506)
- 原 #1 UID 142 降至 #2 (0.251)
- Foremost01: GAME 48.5, LGC-v2 92, LIVEWEB 25.6, NAVWORLD 16.2, PRINT 79.8, SWE-SYNTH 22.2
- 弱项: NAVWORLD 16.2, SWE-SYNTH 22.2 — 我们的数据恰好在这两个环境有优势
- 总矿工数增至 49

**Targon 网络**: 仍然瘫痪。HF/PyPI 全部 Network unreachable。累计探测 ~8 次。

**训练阻塞**: 无变化，等待用户介入或 Targon 恢复。

---

## Loop 迭代 — 2026-03-12 ~18:40 UTC

**排行榜**: 稳定。#1 UID 179 (Foremost01, 0.506)。RLStepone (UID 242) 样本量增至 30+，GAME 49.9 NAVWORLD 25.0，潜在威胁。
**Targon 网络**: 第 9 次探测，仍 Network unreachable。
**DynamoDB**: 3.1h，下轮刷新。
**行动**: 无。训练阻塞中。

---

## Loop 迭代 — 2026-03-12 ~19:00 UTC (突破性进展!)

**排行榜**: #1 UID 142 (AnastasiaFantasy, 0.505) 夺回。Foremost01 (UID 179) 降至 #2。

**Targon 网络突破**:
- **网络是间歇性的，不是完全死亡！** 容器启动后约 20 秒有短暂网络窗口
- apt-get 成功（47MB, 4s），pip install 也成功（所有依赖包括 torch 2.10.0）
- 关键改进: 在 setup_and_train 中加了网络等待循环 + pip 重试 + HF 下载重试
- 第一次尝试: pip 成功但 HF 下载阶段网络又断 → 容器被缩容
- 第二次尝试: 加了 HF 下载重试逻辑，容器 `serv-u-1324508-c7dlf9ms1s0ipwev` 启动中

**启动脚本改进**:
1. 网络等待: 60×10s 循环探测 `/dev/tcp/pypi.org/443`
2. apt-get: 一次成功（网络在 20s 后恢复）
3. pip install: `--retries 10 --timeout 120` + 外层 5 次重试
4. HF 下载: 5 次重试 + 文件存在验证
5. 每步失败都有 30s 等待再重试

**训练配置**: SFT, enhanced_mixed_sft.jsonl (5600条), lr=1e-4, epoch=1, QLoRA r=64, max_len=8192
**目标 HF**: nomooko/affine-qwen3-32b-v4

---

## Loop 迭代 — 2026-03-12 ~20:00-21:30 UTC (持续攻坚 Targon 网络)

**排行榜**: #1 UID 142 (0.507)。Foremost01 掉出 top 10。RLStepone (UID 242) GAME 50.88。

**Targon 网络深入分析**:
- 网络是**间歇性**的: 启动后 ~30-60s 有短暂窗口
- apt-get update+install (47MB) 每次都在窗口内成功
- pip install ALL (包含 torch 2GB) 成功过 1 次（容器 hyuzso4mpb9j70gk）
- HF 数据下载 (42MB) 用 stdlib urllib 每次都在窗口内成功
- **核心瓶颈**: torch 2GB 下载需要持续网络，但窗口长度不一致

**尝试过的方案**:
| 方案 | 结果 |
|------|------|
| 数据先下载, pip 后装 | 数据 OK, pip 失败(网络断) |
| 数据+pip 并行 | 第一版有 bash `&` bug, 第二版仍 pip 超时 |
| 逐包 pip install | 理论可行但未验证成功 |
| PyTorch 官方镜像 | Targon 不支持(500 error) |

**关键代码改进**:
- 网络等待循环 (60×10s)
- `(cmd &)` 子shell后台化避免 `&` 全链后台 bug
- urllib stdlib 直接下载 HF 数据（绕过 huggingface_hub 库）
- 并行下载+安装策略
- pip 多层重试 (retries=10, timeout=300, 外层3次)

**结论**: Targon serverless 的网络限制是根本性的。需要预装 PyTorch 的镜像（Targon 不支持），或外部 GPU 资源。

**累计成本**: 约 $15-20（~10 个容器，各运行 10-30 分钟）

---

## Loop 迭代 — 2026-03-12 ~22:00 UTC (最终结论)

**排行榜**: 新 #1 = UID 45 (Infinite3214, 0.508)。竞争持续加剧。

**Targon 最终结论**: 再次尝试 torch-first 策略（独占带宽），仍然失败。
- 约 15 次容器尝试，累计成本 ~$25
- pip install torch 2GB 只成功过 1 次（网络窗口不可控）
- PyTorch 镜像 Targon 返回 500
- **Targon serverless 在当前网络状态下无法用于训练**

**当前阻塞**: 需要用户提供替代 GPU 资源。不再在 Targon 上重试。

---

## Loop 迭代 — 2026-03-12 ~20:50 UTC

**排行榜**: #1 UID 45 (Infinite3214, 0.508) 稳定。
**Targon**: 不再尝试。等待用户提供替代资源。
**DynamoDB 刷新**: 完成。GAME 930(+24), NAVWORLD 116(+37), SWE-SYNTH 454(+10), LIVEWEB 997(+70)。
**下一步**: 等待 GPU 资源。数据持续累积中。

---

## 🎉 Targon 训练突破 — 2026-03-12 21:15 - 2026-03-13 01:15 UTC

### 解决 Targon 训练的 4 个关键 Bug

**Bug 1: Targon 不支持 pytorch 镜像 → 已修复**
- `pytorch/pytorch:2.5.1-cuda12.4-cudnn9-devel` 现在可以成功启动
- 之前返回 500，可能是 Targon 平台更新修复了

**Bug 2: pip install 网络不可靠 → 离线 wheel bundle 方案**
- 预先下载所有 Python 依赖的 wheel 文件 (202MB tar.gz)
- 上传到 HF dataset repo (`nomooko/affine-sft-data/ml-deps.tar.gz`)
- 容器内用 urllib (可靠) 下载，然后 `pip install --no-index --find-links`
- urllib 下载 229MB 在 Targon 容器内 ~30 秒完成

**Bug 3: bitsandbytes 版本过旧 → 升级到 0.49.2**
- wheel bundle 初始包含 bitsandbytes 0.42.0
- transformers 要求 >= 0.46.1
- 更新 wheel bundle 后训练脚本可以正常加载 4-bit 模型

**Bug 4: 模型下载 65GB 太大 → 预量化模型**
- 原始 Qwen/Qwen3-32B 需下载 ~65GB (16 safetensors) 然后运行时量化
- 改用 `unsloth/Qwen3-32B-bnb-4bit` (4 safetensors, ~18GB)
- 下载时间从 10-30 分钟缩减到 ~90 秒

**Bug 5: OOM 崩溃 → 保守内存配置**
- batch=2, seq=8192, packing=True → 容器启动后训练立即 OOM
- batch=1, seq=4096, packing=False → 训练可以启动但 step 10 后 OOM
- **最终配置**: batch=1, seq=2048, LoRA r=16, packing=False → 稳定运行

### 新增 HTTP 状态监控
- 训练脚本写 `/tmp/health/status.json`，通过 http.server 暴露
- 可以实时查看：phase, step, loss, epoch, error
- 解决了 Targon 日志 API 对 pytorch 镜像不返回日志的问题

### 当前训练状态
- **容器**: serv-u-1324508-uzbtmnami13fvoz7
- **数据**: enhanced_mixed_sft.jsonl (5600 samples)
- **模型**: unsloth/Qwen3-32B-bnb-4bit
- **配置**: lr=1e-4, batch=1, grad_accum=16, seq=2048, LoRA r=16/alpha=32, packing=False
- **进度**: Step 20/350, loss 0.921→0.689, 每步 ~38 秒
- **预计完成**: ~01:00 + 350×38s/3600 ≈ 4.7h → ~05:40 UTC
- **HF 备份**: nomooko/affine-qwen3-32b-v4
- **成本**: $2.40/hr × ~4.7h ≈ $11.3

### 累计 Targon 成本
- 之前失败尝试: ~$25
- 本次调试 (5 containers): ~$5
- 训练 (预计): ~$11
- **总计**: ~$41

---

## 循环报告 — 2026-03-13 07:00 UTC

### 排行榜
| Rank | UID | GAME | LGC-v2 | LIVEWEB | NAVWORLD | PRINT | SWE-SYNTH |
|------|-----|------|--------|---------|----------|-------|-----------|
| 1 | 45 Infinite3214 | 47.77 | 91.60 | 25.54 | 19.61 | 85.87 | 20.83 |
| 2 | 153 vera6 | 50.35 | 92.50 | 24.17 | 22.18 | 83.98 | 15.62 |
| 3 | 142 AnastasiaFantasy | 41.57 | 78.00 | 16.97 | 23.91 | 73.82 | 31.25 |

### 训练状态
- **v4**: step 60/350, loss 0.50, **暂停** — Targon 平台不可用
- checkpoint-60 安全存储在 HF `nomooko/affine-qwen3-32b-v4`
- Resume 机制代码已就绪

### Targon 平台状况
- **完全不可用**: 连空容器（echo+sleep）都无法响应 HTTP
- 测试了 H200-small, H200-medium, H100-small，全部 3-6 min 崩溃
- 之前同配置跑到 step 60（01:15-02:49 UTC），03:00 后开始异常
- 已知问题: transformers 新版 CVE-2025-32434 要求 torch>=2.6

### 行动
1. 终止所有残留容器（已完成）
2. 数据集地址迁移 nomooko → monokoco（已完成）
3. 更新代码中所有 HF 引用（已完成）
4. Resume 机制实现（已完成）

### 阻塞
- Targon 平台恢复时间未知
- 需要替代 GPU 方案或等待平台恢复

### 下一步
- 等 Targon 恢复后，用包含 torch 2.6 的 wheel bundle 重启训练
- 或探索替代 GPU 平台

---

## v5 模型评测 — 2026-03-14

### 评测环境
- **Rental**: rentals-fn3n2qeug900fqif (4×H200)
- **推理**: sglang in venv, monokoco/affine-qwen3-32b-v5-merged, tp=4, port 30000
- **评测**: scripts/eval_envs.py (affinetes SDK, host_network=True)
- **每环境 100 samples**

### v5 训练配置回顾
- QLoRA r=128/alpha=256, lr=1e-4, batch=2×4GPU, grad_accum=4, seq=4096
- 数据: v5_mixed_sft.jsonl (8263 samples → 11872 加权)
- 最终 loss 0.23, eval_loss 0.265, 245 steps

### 评测结果

| 环境 | 样本 | 错误 | 平均分 | 状态 |
|------|------|------|--------|------|
| GAME | 100 | 29 parse errors | 0.1604 | 完成 |
| NAVWORLD | 100 | 0 | 0.0000 | 完成 |
| PRINT* | 100 | 13 | 0.2200 | 完成 |
| SWE-SYNTH | — | — | — | 未完成(rental 回收) |
| LIVEWEB | — | — | — | 未完成(rental 回收) |

*PRINT 不在评测计划内但已跑出结果

#### GAME 细分

| 游戏 | 样本 | 平均分 | 胜场 |
|------|------|--------|------|
| goofspiel | 7 | 1.000 | 7/7 |
| blackjack | 3 | 0.667 | 2/3 |
| leduc_poker | 6 | 0.590 | 4/6 |
| euchre | 3 | 0.500 | 2/3 |
| gin_rummy | 5 | 0.401 | 0/5 |
| checkers | 6 | 0.000 | 0/6 |
| chess | 1 | 0.000 | 0/1 |
| clobber | 11 | 0.000 | 0/11 |
| dots_and_boxes | 4 | 0.000 | 0/4 |
| go | 2 | 0.000 | 0/2 |
| hearts | 6 | 0.000 | 0/6 |
| hex | 4 | 0.000 | 0/4 |
| liars_dice | 8 | 0.000 | 0/8 |
| othello | 3 | 0.000 | 0/3 |
| phantom_ttt | 2 | 0.000 | 0/2 |
| parse_error | 29 | — | — |

#### NAVWORLD: 100% 全零
- 所有 100 个样本得分 0.00
- 模型完全无法执行导航任务
- 可能原因: v5 训练数据中 NAVWORLD 格式问题（文本格式 vs tool_call）

### 关键发现

1. **29% GAME parse error**: 模型输出格式不被环境解析器接受，严重问题
2. **GAME CoT 冲突**: 训练数据中 54.4% 有 `<think>` tags, 45.6% 没有 → 模型输出不一致
3. **NAVWORLD 完全失效**: tool_call 格式训练数据质量问题，模型无法生成正确的工具调用
4. **简单游戏全胜**: goofspiel(7/7), blackjack(2/3) — 规则简单的博弈可以解决
5. **复杂游戏全败**: chess, go, hex, checkers 全 0 — 需要深度搜索的博弈完全无法处理

### v6 训练规划

基于 v5 评测结果，v6 应重点解决:

1. **GAME parse error**: 统一数据格式，消除 think tag 冲突
2. **NAVWORLD**: 使用正确的 tool_call 格式数据
3. **降低 LoRA rank**: r=128→64，减少环境间干扰
4. **聚焦 4 环境**: 只训练 GAME, NAVWORLD, SWE-SYNTH, LIVEWEB (排除 LGC-v2, PRINT)

---

## v6 训练启动 — 2026-03-14

### 训练环境
- **Rental**: rentals-fn3n2qeug900fqif (4×H200)
- **模型**: Qwen/Qwen3-32B (预量化 unsloth/Qwen3-32B-bnb-4bit)
- **脚本**: /root/scripts/train_v6.py

### 数据清洗
- 原始 v6 数据: 7402 samples
- 移除 LGC-v2/PRINT: 1173 条（无 system message 的 Dyck/boolean/math/predict-output 数据）
- 修复 JSONL schema: 统一为 messages-only 格式
- **清洗后**: 6229 samples

| 环境 | 样本数 | 占比 |
|------|--------|------|
| GAME | 2274 | 36.5% |
| NAVWORLD | 1503 | 24.1% |
| SWE-SYNTH | 1275 | 20.5% |
| LIVEWEB | 506 | 8.1% |
| OTHER* | 671 | 10.8% |

*OTHER 可能是跨环境或难以分类的样本

### 训练超参
- lr=5e-5, batch=2, grad_accum=8, epochs=1, seq=4096
- LoRA r=64, alpha=128, packing=True
- save_steps=50, warmup=3%, max_grad_norm=0.3
- HF backup: monokoco/affine-qwen3-32b-v6

### 执行状态
- 训练正常启动，290 steps，~46s/step
- 预计完成: ~3.7h (~$8.9 at $2.40/hr)

### Loss 曲线 (checkpoint-50)
| Step | Loss |
|------|------|
| 10 | 0.8604 |
| 20 | 0.6888 |
| 30 | 0.6309 |
| 40 | 0.4878 |
| 50 | 0.4232 |
| 60 | 0.3570 |
| 70 | 0.3722 |
| 80 | 0.3317 |
| 90 | 0.3127 |
| 100 | 0.3211 |
| 110 | 0.2622 |
| 120 | 0.2669 |
| 130 | 0.2775 |
| 140 | 0.2518 |
| 150 | 0.2372 |
| 160 | 0.2221 |
| 170 | 0.2686 |
| 180 | 0.2196 |
| 190 | 0.2052 |
| 200 | 0.2005 |
| 210 | 0.2115 |
| 220 | 0.2394 |
| 230 | 0.2200 |
| 240 | 0.2297 |
| 250 | 0.2456 |
| 260 | 0.2118 |
| 270 | 0.2254 |
| 280 | 0.2226 |
| 290 | 0.2209 |

### 训练完成 ✅
- **总时间**: 3.7h, 290 steps, 成本 ~$8.9
- **最终 loss**: 0.2209 (从 0.86 下降 74%)
- **HF repo**: monokoco/affine-qwen3-32b-v6 (LoRA adapter, final + checkpoint-200/250/290)
- 对比 v5: loss 0.23 vs v6 loss 0.22（相近，但数据更干净、无 LGC-v2/PRINT 污染）

### 合并 + 评测启动
- LoRA 合并完成 (6.5 min)，保存到 /root/merged_model (24 files)
- sglang 部署完成 (tp=4, port 30000)
- 评测启动: GAME + NAVWORLD × 100 samples
- SWE-SYNTH + LIVEWEB 在第一轮完成后启动

### 工具改进
- 新增 `forge rental` CLI 命令组（status/exec/kill/start-training/start-sglang/start-eval/clean-data）
- 减少直接 SSH 操作，提高效率和可复用性

### v6 评测中间结果 (GAME 29/100)
- 23 个有分数（7 个非零），6 个 error
- 暂时均分 ~0.09（v5 为 0.16，退化）
- 原因：v6 数据问题未彻底修复（见下方诊断）

---

## v7 全面诊断 — 源码分析 + 数据审计结果

### 方法论
1. 读取 4 个评测环境源码（affinetes），理解精确格式要求
2. 逐环境审计训练数据，对比格式差异
3. 制定修复方案后才启动训练

### GAME 诊断

**根因：System Prompt 不一致**
- DDB 数据 (995条)：prompt="respond with ONLY the action ID" → assistant=纯数字
- CoT 数据 (1458条)：prompt="use think block" → assistant=think+数字
- 13.9% CoT 数据的 prompt 写"ONLY"但 assistant 仍带 think tag（直接矛盾）
- 混合训练 → 模型不知道该用哪种格式 → 29% parse error

**数据质量问题**：
- DDB: 20 条脏数据（格式污染：`.3`, `".6`, 长文本残留）
- CoT: 35 条截断 think tag，1 条特殊 token 泄露
- 游戏覆盖不匹配：CoT 缺 hex/othello/clobber/gin_rummy/liars_dice

**评测环境实际行为**：
- `strip_think_tags=True`：会自动剥离 think tag
- 2 次 retry 机制：即使第一次输出错误也有机会纠正
- 所以 CoT 格式本身不是问题，问题是 system prompt 不一致

### NAVWORLD 诊断

**根因：59.7% 样本缺少 direction 工具调用**
- 评测要求必须调用 poi_search + weather + direction 三个工具
- distill_all.jsonl (1503条) 中只有 605 条包含 direction
- 训练这些数据 → 模型学到"不调用 direction" → 评测扣分

**navworld_sft.jsonl (130条) 完全不可用**：
- 使用文本模拟格式（"调用工具: xxx"），不是标准 function calling
- 没有 tool_calls 字段、没有 role=tool
- 混入训练会教模型输出错误格式

**其他问题**：
- 8 条污染样本（文本伪工具调用）
- 7 条 final plan <800 字

### SWE-SYNTH 诊断
- 格式：THOUGHT + 单个 bash 代码块
- **不支持 think tag**（与 THOUGHT 格式冲突）
- 二值评分（0 或 1）
- 数据待审计

### LIVEWEB 诊断
- 格式：自由思考 + JSON action 对象
- 支持 think tag
- 大部分数据 >16K tokens（截断后无法训练）
- 数据待审计

---

## v7 修复方案

### GAME 修复
1. **统一 system prompt 为 CoT 版**（评测会自动剥离 think tag）
2. DDB 数据：保留纯数字格式，但统一 system prompt 为 CoT 版 → 让模型学"即使 prompt 说 think，也可以直接输出数字"
3. CoT 数据：修复 13.9% 错误 prompt
4. 清洗 20 条 DDB 脏数据 + 35 条截断 CoT
5. 目标：~2400 条干净 GAME 数据

### NAVWORLD 修复
1. **只保留包含 poi_search + weather + direction 的样本**（~605 条）
2. 删除 navworld_sft.jsonl（文本格式完全不可用）
3. 清洗 8 条污染 + 7 条短 plan
4. 重新蒸馏补充 direction 覆盖数据到 1000+
5. 目标：~600 条干净数据（短期），1000+（蒸馏补充后）

### SWE-SYNTH 修复
1. 确保 system prompt 与评测一致
2. 确保无 think tag（使用 THOUGHT 格式）
3. 保持现有 ~1275 条

### LIVEWEB 修复
1. 过滤 ≤16K chars 的样本
2. 确保 JSON action 格式正确
3. 现有数据量可能不足（大部分超长）
4. 如可用数据 <100 条，考虑不纳入 v7

### 超参修正
- lr: 5e-5 → **1e-4**（v6 的 5e-5 太低，历史验证 1e-4 更好）
- HF_TOKEN: 确保正确 export

---

## v7 训练 — 2026-03-14

### 数据
- 4809 条，4 环境（GAME 2417, SWE-SYNTH 1350, NAVWORLD 605, LIVEWEB 437）
- 所有已知问题已修复，datasets 加载验证通过

### 超参
- lr=1e-4, batch=2, grad_accum=8, epochs=1, seq=4096
- LoRA r=64, alpha=128, packing=True
- HF backup: monokoco/affine-qwen3-32b-v7（自动上传已验证）

### Loss 曲线
| Step | Loss | vs v6 |
|------|------|-------|
| 10 | 0.7922 | 0.8604 |
| 20 | 0.5996 | 0.6888 |
| 30 | 0.3645 | 0.6309 |
| 40 | 0.3428 | 0.4878 |
| 50 | 0.3044 | 0.4232 |

| 60 | 0.2730 | 0.3570 |
| 70 | 0.2669 | 0.3722 |
| 80 | 0.2422 | 0.3317 |
| 90 | 0.2190 | 0.3127 |
| 100 | 0.2124 | 0.3211 |
| 110 | 0.2160 | 0.2622 |
| 120 | 0.2108 | 0.2669 |
| 130 | 0.1988 | 0.2775 |
| 140 | 0.2048 | 0.2518 |
| 150 | 0.1591 | 0.2372 |
| 160 | 0.1876 | 0.2221 |
| 170 | 0.1581 | 0.2686 |
| 180 | 0.1658 | 0.2196 |
| 190 | 0.1841 | 0.2052 |
| 200 | 0.1761 | 0.2005 |

| 210 | 0.1766 | 0.2115 |
| 220 | 0.1769 | 0.2394 |
| 230 | 0.1776 | 0.2209 |

### 训练完成 ✅
- **总时间**: 3.1h, 230 steps, 成本 ~$7.4
- **最终 loss**: 0.1776 (vs v6 0.2209, 改善 20%)
- **HF repo**: monokoco/affine-qwen3-32b-v7 (自动上传, final + checkpoint-150/200/230)
- **收敛速度**: v7 step 50 (0.30) ≈ v6 step 90 (0.31), 快 ~2x

v7 收敛显著快于 v6。

### v7 GAME 评测中间分析 (40/100)

**整体**: mean=0.030, error rate=11% (vs v5 29%)

**按游戏细分**:
| 游戏 | n | 非零 | mean | 可学性 |
|------|---|------|------|--------|
| leduc_poker | 2 | 2/2 | 0.345 | ✅ 策略有效 |
| euchre | 2 | 1/2 | 0.190 | ✅ 部分有效 |
| othello | 8 | 0/8 | 0.000 | 🟡 需更好策略 |
| hex | 5 | 0/5 | 0.000 | 🟡 需更好策略 |
| go | 6 | 0/6 | 0.000 | ❌ LLM 无法学 |
| checkers | 4 | 0/4 | 0.000 | ❌ LLM 无法学 |
| gin_rummy | 2 | 0/2 | 0.000 | 🟡 需策略数据 |
| solitaire | 3 | 0/3 | 0.000 | ❌ 单人游戏 |

### v7 GAME 最终结果 (100/100)

**总分: mean=0.145, 27/88 非零 (31%), 12 error (12%)**

| 游戏 | n | 胜率 | mean | 评价 |
|------|---|------|------|------|
| goofspiel | 2 | 100% | 1.000 | ✅ 完美 |
| leduc_poker | 12 | 100% | 0.579 | ✅ 策略有效！|
| bridge | 1 | 100% | 0.480 | 样本少 |
| euchre | 8 | 63% | 0.297 | 可提升 |
| gin_rummy | 5 | 20% | 0.088 | 🔴 需 bot 数据 |
| othello | 12 | 0% | 0.000 | 🔴 需 bot 数据 |
| liars_dice | 4 | 0% | 0.000 | 🔴 需 bot 数据 |
| hex | 7 | 0% | 0.000 | 🔴 需 bot 数据 |
| go/chess/checkers | 15 | 0% | 0.000 | ❌ LLM 无法学 |

**关键结论**:
- parse error 29%→12% ✅ (system prompt 统一修复有效)
- leduc_poker 12/12 全胜 ✅ (证明 SFT 可学博弈策略)
- v8 用 game_bot 策略数据（7 游戏 1687 条）应让 gin_rummy/othello/hex/liars_dice 突破 0%

### v7 NAVWORLD 结果: 全零（18/18 = 0.00）

**根因诊断**:
1. API key 问题（已修复）：eval 脚本未传入 AMAP_MAPS_API_KEY
2. **数据格式根因**：v7 训练时将 tool_calls 序列化为 `<tool_calls>JSON</tool_calls>` 文本，
   但 Qwen3 原生 tool calling 格式是 `<tool_call>JSON</tool_call>` + `<tool_response>` + `<tools>`。
   模型学到的格式与评测环境期望的不匹配。

**v8 修复方案**：用 `tokenizer.apply_chat_template(messages, tools=tools)` 生成训练文本，
确保 tool calling 格式与 Qwen3 原生完全一致。

---

## v8 训练 — 2026-03-14

### 关键改进 vs v7
1. **NAVWORLD**: 用 `apply_chat_template(tools=)` 生成原生 `<tool_call>` 格式（vs v7 的文本序列化）
2. **GAME**: 新增 2193 条 game_bot 策略数据（7 游戏，程序化策略 bot 生成）
3. **数据格式**: 所有数据用 `text` 字段（apply_chat_template 输出），与 Qwen3 tokenizer 完全对齐

### 数据 (7002 条)
| 来源 | 条数 |
|------|------|
| GAME v7 clean | 2417 |
| GAME bot (7游戏) | 2193 |
| SWE-SYNTH | 1350 |
| NAVWORLD (原生 tool_call) | 605 |
| LIVEWEB (原生 tool_call) | 437 |

### 超参
- lr=1e-4, batch=2, grad_accum=8, epochs=1, seq=4096
- LoRA r=64, alpha=128, packing=True
- HF: monokoco/affine-qwen3-32b-v8 (private, 自动上传)

### Loss 曲线
| Step | v8 | v7 |
|------|-----|-----|
| 10 | 0.6741 | 0.7922 |
| 20 | 0.5252 | 0.5996 |
| 30 | 0.3892 | 0.3645 |
| 40 | 0.3318 | 0.3428 |
| 50 | 0.2796 | 0.3044 |

| 60 | 0.2610 | 0.2730 |
| 70 | 0.2195 | 0.2669 |
| 80 | 0.2121 | 0.2422 |
| 90 | 0.1813 | 0.2190 |
| 100 | 0.1847 | 0.2124 |

| 110 | 0.1621 | 0.2160 |
| 120 | 0.1619 | 0.2108 |
| 130 | 0.1509 | 0.1988 |
| 140 | 0.1481 | 0.2048 |
| 150 | 0.1313 | 0.1591 |

| 160 | 0.1417 | 0.1876 |
| 170 | 0.1538 | 0.1581 |
| 180 | 0.1320 | 0.1658 |
| 190 | 0.1389 | 0.1841 |
| 200 | 0.1196 | 0.1761 |

| 210 | 0.1439 | 0.1766 |
| 220 | 0.1333 | 0.1769 |
| 230 | 0.1289 | 0.1776 |
| 240 | 0.1251 | — |
| 250 | 0.1140 | — |

| 260 | 0.1176 | — |
| 270 | 0.1102 | — |
| 280 | 0.1194 | — |
| 290 | 0.1158 | — |
| 300 | 0.1084 | — |
| 310 | 0.0970 | — |
| 320 | 0.1145 | — |

### 训练完成 ✅
- **总时间**: 4.4h, 323 steps, 成本 ~$10.6
- **最终 loss**: ~0.11 (vs v7 0.18, v6 0.22)
- **HF**: monokoco/affine-qwen3-32b-v8 (private, 自动上传)
- v8 loss 历史最低，全程优于 v7

### v8 评测
- 首轮评测因 Docker 容器重启问题（旧容器状态腐化）全零——不是模型问题
- 直接 API 测试确认模型正常：GAME 输出纯数字✅, NAVWORLD 输出 `<tool_call>`✅
- 清理容器后重跑 20 samples GAME：
  - mean=0.090, 6/18 非零 (33%), 2 error (10%)
  - **gin_rummy 2/2 全胜 (0.375)** — v7 是 0/5！bot 策略数据生效！
  - **hearts 1/1 (0.33)** — v7 只有 0.083
  - othello/hex/go 仍然 0%——需要更强策略或放弃

### NAVWORLD 全零根因最终定位
- **sglang 缺少 `--tool-call-parser` 参数**
- 模型正确输出 `<tool_call>` 文本，但 sglang 没有解析为 OpenAI `tool_calls` 字段
- 评测环境看到 `tool_calls=None` → 认为没有工具调用 → 0 分
- **修复**: 启动 sglang 时加 `--tool-call-parser qwen25`
- 修复后验证: `tool_calls` 字段正确返回 ✅
- NAVWORLD 重新评测结果 (tool-call-parser 修复后):
  - **mean=0.096, 6/18 非零 (33%)** — 历史首次突破零分！🎉
  - 分数分布: 0.22, 0.23, 0.27, 0.28, 0.28, 0.45
  - v5/v6/v7 全部 0% → v8 33% 非零
  - 根因链：训练数据格式(apply_chat_template) + sglang(tool-call-parser) 双修复

### v8 完整评测总结

| 环境 | 样本 | Mean | 非零率 | Error |
|------|------|------|--------|-------|
| GAME | 20 | 0.090 | 33% | 10% |
| NAVWORLD | 20 | 0.087 | 30% | 0% |

**vs v7**: GAME 类似，NAVWORLD 从 0 突破到 0.087。
**vs 排行榜**: #1 NAVWORLD ~20 分，v8 的 8.7 分有竞争力但还需提升。

### SWE-SYNTH / LIVEWEB 评测结果
- **SWE-SYNTH**: 无法本地评测（需要 breaker service 预生成 tasks）
- **LIVEWEB**: 无法本地评测（task_id 范围限制，需预定义 task 集）
- 这两个环境只能通过部署到排行榜验证

### v8 最终结论
- **可评测环境**: GAME 0.090 (20s), NAVWORLD 0.087 (20s, 首次突破)
- **不可本地评测**: SWE-SYNTH, LIVEWEB（需部署验证）
- 合并模型已上传 HF: `monokoco/affine-qwen3-32b-v8-merged` (private, 65GB)
- 待用户授权部署到 Chutes

## v9 训练 — 2026-03-15

### 改进 vs v8
1. **LGC-v2 (3353) + PRINT (2899) 重新纳入**（排行榜仍在评分，几何平均不能缺）
2. **NAVWORLD 新 key 数据 28 条**补充（旧 key 失效→工具返回空数据已修复）
3. 数据量 13282 条（vs v8 7002, +90%）

### 数据 (13282 条)
| 环境 | 条数 | 占比 |
|------|------|------|
| GAME (v7 clean + bot) | 4610 | 34.7% |
| LGC-v2 | 3353 | 25.2% |
| PRINT | 2899 | 21.8% |
| SWE-SYNTH | 1350 | 10.2% |
| NAVWORLD | 633 | 4.8% |
| LIVEWEB | 437 | 3.3% |

### Loss 曲线
| Step | v9 | v8 |
|------|-----|-----|
| 10 | 0.6755 | 0.6741 |
| 20 | 0.5642 | 0.5252 |
| 30 | 0.4859 | 0.3892 |
| 40 | 0.3709 | 0.3318 |
| 50 | 0.2829 | 0.2796 |

| 60 | 0.3118 | 0.2610 |
| 70 | 0.2419 | 0.2195 |
| 80 | 0.2880 | 0.2121 |
| 90 | 0.2563 | 0.1813 |
| 100 | 0.2288 | 0.1847 |

| 110 | 0.2187 | 0.1621 |
| 120 | 0.2266 | 0.1619 |
| 130 | 0.1809 | 0.1509 |
| 140 | 0.1896 | 0.1481 |
| 150 | 0.2104 | 0.1313 |

| 160 | 0.1736 | 0.1417 |
| 170 | 0.1996 | 0.1538 |
| 180 | 0.1815 | 0.1320 |
| 190 | 0.1934 | 0.1389 |
| 200 | 0.2045 | 0.1196 |

| 210 | 0.1663 | 0.1439 |
| 220 | 0.1776 | 0.1333 |
| 230 | 0.1760 | 0.1289 |
| 240 | 0.1707 | 0.1251 |
| 250 | 0.1769 | 0.1140 |

| 260 | 0.1742 | 0.1176 |
| 270 | 0.1639 | 0.1102 |
| 280 | 0.1680 | 0.1194 |
| 290 | 0.1556 | 0.1158 |
| 300 | 0.1672 | 0.1084 |

| 310 | 0.1744 | 0.0970 |
| 320 | 0.1807 | 0.1145 |
| 330 | 0.1528 | — |
| 340 | 0.1652 | — |
| 350 | 0.1532 | — |

| 360 | 0.1465 | — |
| 370 | 0.1498 | — |
| 380 | 0.1367 | — |
| 390 | 0.1379 | — |
| 400 | 0.1425 | — |

### 训练完成 ✅
- **总时间**: 5.7h, 421 steps, 成本 ~$13.7
- **最终 loss**: ~0.14 (vs v8 0.11, v7 0.18)
- **HF**: monokoco/affine-qwen3-32b-v9 (private, 自动上传)
- v9 loss 比 v8 高但覆盖 6 个环境（含 LGC-v2/PRINT）

### v9 GAME 评测（并发4 + timeout 7200s + 只评训练游戏）
- 32/100 samples, 12 非零 (38%), mean=**0.187**, 0 error
- vs 旧配置（串行 + 600s timeout + 全22游戏）: mean 0.10→0.19, 质的飞跃
- 关键发现: 58min 游戏得 0.33 分——旧 timeout 会丢掉这些分数
- 2 个满分 (1.00)，最高单局 0.62
- LGC-v2/PRINT 未伤害 GAME 能力

### v9 GAME 最终中间结果 (74/100, rental 断连)
- 74 samples, 27 非零 (36%), mean=**0.171**, 趋势充分稳定
- NAVWORLD 评测未开始（rental 断连前仍在 GAME 阶段）
- Rental 不可达 (2026-03-15 ~21:00)，模型安全在 HF

### 部署就绪
- v8: `monokoco/affine-qwen3-32b-v8-merged` (private)
- v9: `monokoco/affine-qwen3-32b-v9-merged` (private)
- 待用户授权部署到 Chutes

### Rental 丢失 + 恢复
- 旧 rental 断连，新 rental `rentals-w58tlzhv9xyh3dis` 启用
- 解决 sglang CUDA toolkit 依赖问题（安装 cuda-nvcc-12-8 + cuda-cudart-dev-12-8）

### v9 完整评测结果（并发4, timeout 7200s, 只评训练游戏）

| 环境 | 样本 | 非零 | Mean | 备注 |
|------|------|------|------|------|
| GAME | 87 | 36 (41%) | **0.201** | 排行榜约 20 分 |
| NAVWORLD | 100 | 23 (23%) | **0.052** | 排行榜约 5 分 |

**vs v8**: NAVWORLD 从 0.087 (20s) → 0.052 (100s)。v8 样本少方差大，100 samples 的 0.052 更可靠。
**vs v5**: NAVWORLD 从 0.000 → 0.052，GAME 从 0.145 (600s timeout) → 0.201 (7200s timeout)

---

## v10 训练 — 2026-03-16

### 改进 vs v9
1. **MemoryGym 500 条**新增（预上线环境，提前训练）
2. 数据量 13733 条（vs v9 13282, +MemoryGym 500）
3. 覆盖 7 个环境：GAME, NAVWORLD, SWE-SYNTH, LIVEWEB, LGC-v2, PRINT, MemoryGym

### 训练状态
- 新 rental `rentals-w58tlzhv9xyh3dis` (4×H200)
- 解决了 CUDA toolkit 依赖问题（cuda-nvcc-12-8 + cuda-cudart-dev-12-8）
- HF: monokoco/affine-qwen3-32b-v10 (private)

### 训练完成 ✅
- **总时间**: 9.1h, 441 steps
- **最终 loss**: ~0.19 (收敛在 0.19-0.23)
- v10 loss 比 v9 高约 0.05（MemoryGym 新环境拉高），但 7 环境全覆盖

### v10 GAME 最终结果
- 99 samples, **41 非零 (41%)**, mean=**0.220**
- vs v9: 0.220 vs 0.201 — v10 略优，MemoryGym 未影响 GAME
### v10 完整评测结果

| 环境 | 样本 | 非零 | Mean | vs v9 |
|------|------|------|------|-------|
| GAME | 99 | 41 (41%) | **0.220** | 0.201 (+9%) |
| NAVWORLD | 100 | 28 (28%) | **0.051** | 0.052 (持平) |

**结论**: v10 GAME 略优于 v9, NAVWORLD 持平。MemoryGym 500 条加入无负面影响。
模型部署就绪: `monokoco/affine-qwen3-32b-v10-merged` (private)

---

## v11 训练 — 2026-03-17

### 改进 vs v10
1. **NAVWORLD**: 632→2154 条 (+240%)，全部新 API key 生成，100% direction 覆盖
2. 数据量 15273 条（vs v10 13733, +11%）

### 训练状态
- 新 rental `rentals-w58tlzhv9xyh3dis` (4×H200)
- HF: monokoco/affine-qwen3-32b-v11 (private)

### 训练完成 ✅
- **总时间**: 11.1h, 538 steps
- **最终 loss**: ~0.17 (收敛在 0.15-0.19，优于 v10 的 0.19)

### v12 规划
- **seq_length 提升到 8192**: SWE-SYNTH 98% 数据在 4096 下被截断，导致模型从未学到完整修复流程
- **用数据 Agent 的正式配比**: 8550 条均衡配比（vs 当前拼凑的 15273 条）
- **NAVWORLD 2648 条**: 数据 Agent 持续扩量，100% 真实 POI + direction

### v11 GAME 最终结果
- 100 samples, **39 非零 (39%)**, mean=**0.226**
- vs v10: 0.226 vs 0.220 — 持平
### v11 完整评测结果

| 环境 | 样本 | 非零 | Mean | vs v10 |
|------|------|------|------|--------|
| GAME | 100 | 39 (39%) | **0.226** | 0.220 (+3%) |
| NAVWORLD | 100 | 28 (28%) | **0.057** | 0.051 (+12%) |

NAVWORLD 3.4x 数据增量→12% 提升。模型部署就绪: `monokoco/affine-qwen3-32b-v11-merged` (private)

---

## v12 训练 — 2026-03-18

### 改进 vs v11
1. **seq_length 8192** (vs 4096): SWE-SYNTH 98%数据不再被截断
2. **batch=1, grad_accum=16**: 适应更长序列
3. NAVWORLD 2248 条（持续增长）

### 训练状态
- 434 steps, seq=8192, HF: monokoco/affine-qwen3-32b-v12 (private)

---

---

### v8 可用数据

| 来源 | 条数 |
|------|------|
| GAME v7 clean (DDB+CoT) | 2417 |
| GAME bot (7游戏策略) | 1687 |
| NAVWORLD v7 clean | 605 |
| SWE-SYNTH v7 clean | 1350 |
| LIVEWEB v7 clean | 437 |
| **合计** | **6496** |（lr=1e-4 vs 5e-5）。v7 step 100 loss (0.21) 已优于 v6 最终 loss (0.22)。HF 自动上传正常工作。

---
