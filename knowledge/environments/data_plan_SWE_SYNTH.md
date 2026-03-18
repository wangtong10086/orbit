# SWE-SYNTH 数据计划与深度分析

> 最后更新: 2026-03-18 16:15 UTC | 优先级: P1 (seq=8192 免费午餐) | 状态: v2 训练中

## 1. 环境概述

SWE-SYNTH 评估 LLM 的多轮代码调试与修复能力。模型在 Docker 容器中通过 bash 命令与代码交互，需要定位 bug、编写修复、验证通过。

**评分**: 二值 0/1（pass/fail），无部分分。
**格式**: THOUGHT 前缀 + 单个 bash code block。**禁止 `<think>` 标签。**
**部署**: 需要 Docker socket 挂载，外部 breaker service 预生成任务。不可本地 eval。

## 2. 当前数据状态

### 2.1 总体概况 (canonical: 983 条)

| 指标 | 值 |
|------|-----|
| 条数 | 983（清理后） |
| 分数 | 全部 score=1.0（仅成功解决方案） |
| 来源 | DDB 提取 |
| System prompt | **仅 1 个**（542 chars，完全相同） |
| Think tags | 0（已清理 368 条污染数据） |

### 2.2 序列长度分析（关键）

| Token 范围 | 条数 | 占比 | 说明 |
|-----------|------|------|------|
| ≤2K | 0 | 0% | 无极短对话 |
| 2K-4K | 24 | 2.4% | v1 (seq=4096) 仅完整容纳这些 |
| 4K-8K | 437 | 44.5% | seq=8192 新增 |
| 8K-16K | 517 | 52.6% | 超过半数，需 seq=16384 |
| >16K | 5 | 0.5% | 极少数超长 |

**中位 8,310 tokens，平均 9,033 tokens。**

**seq=4096→8192 是"免费午餐"**: 完整对话从 24→461 条 (19x 提升)，不需新数据。

### 2.3 对话轮数分析

| 指标 | 值 |
|------|-----|
| 最少轮数 | 3 轮 |
| 最多轮数 | 30 轮 |
| 中位 | 13 轮 |
| 平均 | 14.3 轮 |
| 消息总数 | 范围 7-61，中位 27 |

分布呈钟形，峰值在 11 轮。每条数据的 user 和 assistant 消息数量严格相等（配对）。

### 2.4 Bash 命令多样性

总计 14,074 个 bash code blocks:

| 命令类型 | 出现次数 | 占比 | 用途 |
|---------|---------|------|------|
| sed | 3,493 | 24.8% | 文件编辑（主修复手段） |
| cat | 2,882 | 20.5% | 文件查看 + heredoc 写入 |
| grep | 2,157 | 15.3% | 代码搜索定位 |
| find | 1,398 | 9.9% | 文件查找 |
| ls | 1,374 | 9.8% | 目录探索 |
| python3 | ~800 | 5.7% | 测试运行 |
| cd | ~500 | 3.6% | 目录切换 |

**关键发现**: 大量 bash blocks 内嵌 Python heredoc (`cat <<'EOF' ... EOF`)，用于:
- 写入测试文件
- 创建修复脚本
- 生成配置文件

纯 bash 占 85%，heredoc 嵌入占 15%。

### 2.5 THOUGHT 格式遵循

- **99.6% 的 assistant 消息以 "THOUGHT" 开头** (14,004/14,061)
- 57 条不以 THOUGHT 开头 — 大多是最终提交消息

### 2.6 Think Tag 状态

**零 `<think>` 标签** — 2026-03-18 已清理 368 条污染数据（334 含 `<think>`, 34 含孤立 `</think>`）。

### 2.7 System Prompt 分析

**仅 1 个唯一 system prompt**，542 字符，所有 983 条完全相同:
```
"You are a helpful assistant that can interact multiple times
with a computer shell to solve programming tasks.
Your response must contain exactly ONE bash code block...
Include a THOUGHT section before your command..."
```

**问题**: 零多样性。模型会过拟合到这个特定 prompt。如果 eval 的 system prompt 有任何变化（措辞、格式），模型表现可能急剧下降。

### 2.8 最终 assistant 消息特征

| 特征 | 占比 |
|------|------|
| 包含 bash block | 100% |
| 包含修复总结语言 | 92.5% |
| 中等长度 (200-1000 chars) | 93.8% |
| 包含验证语言 | 11.4% |
| 典型模式 | THOUGHT 总结 + `git add -A && git diff --cached` |

## 3. 瓶颈根因分析

### 3.1 序列长度截断 (已在 v2 解决)

v1 (seq=4096): 97.6% 数据被截断。模型只学到对话开头（定位 bug），学不到修复过程。
v2 (seq=8192): 47% 数据完整，大幅改善。
理想 (seq=16384): 100% 完整，但 VRAM 成本翻倍。

### 3.2 无负样本

全部 score=1.0。模型只见过成功轨迹，无法学习:
- 避免常见错误路径
- 从错误尝试中恢复
- 区分好的修复方案 vs 差的修复方案

### 3.3 单一 System Prompt

eval 的 system prompt 如果与训练不完全一致，模型可能不遵循 THOUGHT 格式。这是一个脆弱性风险。

### 3.4 竞品差距

| 矿工 | SWE-SYNTH 分 |
|------|-------------|
| affshoot | 53.19 |
| coffie3 | 46.00 |
| AnastasiaFantasy | 40.00 |
| 我们 v10 | ~31 |
| gap to #1 | -22.2 |

差距来源假设:
1. 竞品可能用 seq≥16384（我们 v2 才刚到 8192）
2. 竞品可能有更多高质量数据（DDB 持续积累）
3. 竞品可能用 DPO/RL fine-tuning

### 3.5 不可本地验证

唯一能知道 SWE-SYNTH 分数的方式是部署到排行榜。每次迭代需要 ~$9 训练 + 部署等待，反馈回路极长。

## 4. 行动计划

### v2 (当前): seq=8192，不修改数据
- 983 条，seq=8192
- 完整对话: 24→461 (19x)
- 预期: SWE-SYNTH 31→35-40

### v2a (如果 v2 分数不理想):

| 行动 | 方法 | 预期效果 | 优先级 |
|------|------|---------|--------|
| DDB 新样本提取 | 提取 score≥0.5 且 ≤8192 tokens 的新条目 | +100-300 条高质量数据 | P1 |
| 对话压缩 | 移除冗余中间输出（ls/cat 重复），保留关键修复步骤 | 使更多条目 fit 在 8192 | P2 |
| System prompt 多样化 | 创建 3-5 种等价但措辞不同的 prompt 变体 | 减少过拟合 | P2 |

### v3 (DPO):
- 258 对偏好对已就绪
- chosen: 成功修复 (score=1.0)
- rejected: 失败尝试或次优路径
- 目标: 40→50+

### v4 (seq=16384):
- 解锁剩余 52.6% 数据
- VRAM 需求: ~180GB/GPU（4×H200 可能勉强够）
- 需要评估 VRAM/效果 tradeoff

### 长期研究方向:
1. **失败轨迹生成**: 让模型尝试解决已知问题，收集失败路径作为 DPO rejected
2. **多 system prompt 训练**: 防止 eval prompt 变化导致格式崩溃
3. **bash 命令模式分析**: 成功修复最常用的命令序列模式
4. **合成新任务**: 用已解决任务的模式生成变体（需 breaker service 配合）

## 5. 质量检查清单

- [x] Schema: `{"messages": [...], "env": "SWE-SYNTH", "score": float}`
- [x] 最后消息 role=assistant
- [x] 0 条含 `<think>` 标签
- [x] 99.6% assistant 用 THOUGHT 前缀
- [x] bash code block 完整性 (0 条 assistant 截断)
- [x] System prompt 存在
- [ ] 按 token 分桶，确保 seq_len 内完整 (v2)
- [ ] DDB 新增高分样本提取 (持续)
- [ ] System prompt 多样化 (v2a)

## 6. 关键文件

| 文件 | 条数 | 状态 |
|------|------|------|
| `data/canonical/swe_synth.jsonl` | 983 | v2 训练中 |
| DDB 源 | 11,594 总 | 持续积累 |
| DPO 数据 | 258 对 | v3 就绪 |
