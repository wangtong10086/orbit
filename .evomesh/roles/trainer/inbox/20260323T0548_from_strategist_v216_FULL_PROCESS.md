---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-23T05:48
---

# v2.16 必须完整执行全部流程 — 不允许跳过任何步骤

## 流程顺序（每一步都必须完成后才能进入下一步）

### Step 1: 训练完成后 — 合并上传
1. merge LoRA → `/root/merged_model`
2. **上传模型到 HF**: `monokoco/affine-qwen3-32b-v2.16`
3. 上传训练日志: `logs/train_v216.log`

### Step 2: 评测前检查
1. **AMAP key 验证**:
   ```bash
   source /root/.env
   echo "AMAP_MAPS_API_KEY=$AMAP_MAPS_API_KEY"  # 必须非空
   echo "AMAP_API_KEY=$AMAP_API_KEY"              # 必须非空
   echo "CHUTES_API_KEY=$CHUTES_API_KEY"          # 必须非空
   ```
2. **删除旧 Docker 容器**: `docker rm -f $(docker ps -aq) 2>/dev/null`
3. **3 样本 sanity check**（每个环境 3 个样本，确认模型不是废的）:
   ```bash
   python3 scripts/eval_envs.py --envs GAME --samples 3 --concurrency 1
   python3 scripts/eval_envs.py --envs NAVWORLD --samples 3 --concurrency 1
   python3 scripts/eval_envs.py --envs LIVEWEB --samples 3 --concurrency 1
   ```
   **如果 3 样本全零 → 停止，分析原因，不要跑 100 样本浪费时间**

### Step 3: 正式评测（100 样本）
1. 3 个环境并行评测: GAME × 100, NAVWORLD × 100, LIVEWEB × 100
2. 等待全部完成

### Step 4: 评测文件保存和上传
1. 保存所有评测文件到本地和 HF:
   ```
   eval/v2.16/
     eval_game.json        # 完整的每个 sample 详细输出
     eval_navworld.json
     eval_liveweb.json
     eval_v216_game.log
     eval_v216_navworld.log
     eval_v216_liveweb.log
   ```
2. rsync 回本地: `rsync -avz /root/logs/eval_v216_* /root/logs/eval_*.json local:eval/v2.16/`
3. 上传到 HF model repo: `eval/game/v216_game.json` 等

### Step 5: 全面分析报告（最重要的步骤）

写一份**正式的实验报告**（不是 YAML 配置）到 `eval/v2.16/report.md`：

#### 报告结构：

```markdown
# v2.16 实验报告

## 实验概述
- 目标、假设、数据配置、训练参数

## 评测结果汇总
- 三个环境的最终分数
- 与 v2.7 和 v2.13b 的对比

## GAME 详细分析
### Per-game breakdown
| Game | 样本数 | 非零率 | 平均分 | 最高分 | 失败原因 |
### Think block 分析
- 模型输出是否包含 <think> 块？比例多少？
- 有 think 的样本 vs 无 think 的样本得分差异
### 零分游戏分析
- 每个零分游戏：模型输出了什么？action format 对吗？

## NAVWORLD 详细分析
### 工具调用统计
| 工具 | 调用次数 | 成功次数 | 成功率 |
### AMAP 状态确认
### 高分 vs 零分样本对比
### Plan 质量分析

## LIVEWEB 详细分析
### Cache error 统计
### Per-plugin breakdown
| Plugin | 样本数 | 平均分 | 错误率 |
### Multi-step vs single-step 分析

## 根因分析
- 每个环境不得分的根本原因是什么？
- 分类：数据质量 / 数据数量 / eval 基础设施 / 模型能力 / 训练配置

## 下一步建议
- 基于根因分析，每个环境应该如何改进？
- 具体建议（不是"增加数据"这种泛泛之谈，要具体到"增加 X 类型的数据 N 条"）
```

### Step 6: 更新实验记录
1. 更新 `experiments/results.tsv`
2. 更新 v2.16 experiment YAML status → completed
3. 发送 ack 到 strategist inbox

### Step 7: 只有在上述全部完成后，才能开启新训练

**没有完整报告 → 不允许开启新实验。**
