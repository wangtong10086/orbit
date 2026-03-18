# SWE-SYNTH 数据方案

> 最后更新: 2026-03-18 | 优先级: P0 (免费午餐 — seq=8192) | v1 状态: 训练中

## 现状

| 指标 | 值 |
|------|-----|
| canonical 条数 | 983 (已清洁) |
| v1 用量 | 983 |
| 历史分数 | ~31 (v10) |
| 竞品最高 | 56.84 (affshoot), ~60.61 (deepresearch001) |
| GM 贡献潜力 | 31→40 = **+1.6 GM** (仅改 seq_len) |
| 数据格式 | multi-turn, THOUGHT + bash code block |
| 本地 eval | 不可 (需 breaker service) |

## 评估格式详解 (源码: affinetes)

### 消息结构
```
System: "You are a helpful assistant that can interact multiple times
        with a computer shell to solve programming tasks."
User: "[task description / error output / test results]"
Assistant: "THOUGHT
I can see the issue is in the function foo() where...

```bash
grep -r 'def foo' src/
```"
User: "[command output]"
Assistant: "THOUGHT
Found the bug. The variable should be...

```bash
sed -i 's/old/new/' src/module.py
```"
...重复直到修复完成
```

### 输出格式要求
- **禁止 `<think>` 标签** — 与 THOUGHT 前缀格式冲突
- Assistant 用 `THOUGHT` 前缀做推理 (非 `<think>` 块)
- 每轮恰好一个 bash code block
- 最后一条消息必须是 assistant

### 评分算法
- **二值评分**: 0 或 1 (pass/fail)
- 任务执行: 代码必须成功修复编程问题
- 无部分分 (partial credit)
- 不可本地验证, 仅通过排行榜部署后观察

### Eval 参数
- Timeout: 7200s, Memory: **4GB** (比其他 env 大)
- Concurrency: **1** (串行评估, 非并行)
- Docker image: swe-synth:eval
- 需要挂载 Docker socket: `/var/run/docker.sock` (bind, rw)
- 不可本地 eval (需外部 breaker service 预生成任务)

### 数据清洗规则 (forge/data/sft.py)
- 最少 4 条消息
- 第一条必须是 system
- 至少一条 assistant 回复内容 ≥20 字符
- 移除末尾的 user 消息 (防止模型学习预测 user 输出)
- 剥离所有 `<think>...</think>` 块
- 验证 bash code block 完整性 (截断的 = 不可用)

## 数据质量审计结果

### Think Tag 清理 (已完成)
- 原始: 1,351 条, 其中 334 条 (24.7%) 含 `<think>` 标签
- 清理后: **983 条**, 0 think tags
- 另有 34 条只有 `</think>` 无开标签, 一并移除
- 全部 score=1.0

### 序列长度分析 (清洁数据, 关键)

| seq_len (tokens) | 可完整容纳 | 比例 | 说明 |
|---------|-----------|------|------|
| 4,096 | 32 | **3.1%** | v1 只有 32 条完整对话 |
| 8,192 | 499 | **49.1%** | v2 目标, 15.6x 提升 |
| 16,384 | 1,017 | 100% | 需要更多 VRAM |

**这是全项目最大的"免费午餐"**: 仅改训练参数 (seq_len 4096→8192), 不需新数据, 完整对话从 32→499 条。

## 瓶颈分析

| 瓶颈 | 影响 | 数据 | 解法 | 阶段 |
|------|------|------|------|------|
| seq=4096 截断 | 97% 数据被截断, 模型只学对话开头 | 32/983 完整 | seq=8192 | v2 |
| 竞品差距大 | affshoot 56.84, 我们 ~31 | -25.8 gap | seq + 更多数据 | v2-v3 |
| 无法本地验证 | 只能部署后看榜 | — | 接受现状 | — |
| 数据总量有限 | 983 条 (清洁后) | DDB 持续积累 | 定期提取新高分样本 | 持续 |

## 数据行动方案

### v1: 清洁数据 (当前阶段 — 训练中)
- [x] 清除 think tag 污染: 1,351 → 983 条
- [x] canonical 文件已替换 (claudeuser-owned)
- [x] synth_config.json 已更新
- **注意**: v1 用 seq=4096, 只有 32 条完整对话, 预期 SWE-SYNTH 分数较低

### v2: seq=8192 (已设计, 见 `experiments/v2-swe-synth-seq8192.yaml`)
- **仅改配置**: seq_len 4096→8192
- 完整对话: 32→499 (15.6x)
- VRAM 预估: ~90GB/GPU (H200 144GB, 应该够)
- 训练时间: ~2x v1
- 成本: ~$18
- **预期 ROI**: SWE-SYNTH ~31→35-40 (+1.6 GM)
- **阻塞**: 等 v1 结果确认 baseline

### v2 附加: 数据增量 (并行)
- DDB 持续积累新样本 (当前 11,594 总量, avg score 0.335)
- 定期提取 score≥0.5 且 ≤8192 tokens 的新条目
- 考虑对话压缩: 移除冗余中间输出, 保留关键修复步骤

### v3: DPO
- 258 对偏好对可用
- 用于推送 SWE-SYNTH 超过 SFT 天花板
- 目标: 40→50+ 分 (接近 affshoot 56.84)

## 格式要求详解

```
System: [task description — 项目名、bug 描述、测试命令]
User: [error output / test failure / command result]
Assistant: THOUGHT
[对问题的分析推理]

```bash
[调查或修复的命令]
```

User: [命令输出结果]
Assistant: THOUGHT
[进一步分析]

```bash
[下一步修复命令]
```
...重复直到修复完成
```

**格式红线**:
- 不允许 `<think>` 标签 (与 THOUGHT 前缀冲突)
- 每轮恰好一个 bash code block
- 最后一条消息必须是 assistant
- bash 代码块必须完整 (有开有闭)

## 数据质量检查清单

- [x] `datasets.load_dataset('json', data_files=...)` 成功
- [x] Schema: `{"messages": [...], "env": "SWE-SYNTH", "score": float}`
- [x] 最后一条消息 role=assistant
- [x] 0 条含 `<think>` 标签 (已清理)
- [x] 所有 assistant 消息用 THOUGHT 前缀
- [x] bash code block 格式完整
- [x] System prompt 存在
- [ ] 按 token 长度分桶, 仅用 ≤seq_len 的条目 (v2)

## 准备文件

| 文件 | 位置 | 条数 | 状态 |
|------|------|------|------|
| canonical (已清洁) | `data/canonical/swe_synth.jsonl` | 983 | claudeuser-owned, v1 使用中 |
| DPO 数据 | — | 258 对 | 可用 (v3) |
| DDB 源 | DynamoDB | 11,594 总 | 持续积累中 |
