# LIVEWEB 数据方案

> 最后更新: 2026-03-18 | 优先级: P3 (结构性无解, 仅维持覆盖) | v1 状态: 训练中

## 现状

| 指标 | 值 |
|------|-----|
| canonical 条数 | 430 (全量), 18 (短条目) |
| v1 用量 | 18 (短条目, 安全网) |
| 历史分数 | ~24 (v11) |
| 竞品最高 | 19.36 (affshoot) |
| GM 贡献潜力 | 24→24 = **0 GM** (已领先, 维持即可) |
| 数据格式 | free think + JSON action object |
| 本地 eval | 不可 (task_id 范围限制) |

**关键发现**: 我们 v11 ~24 分**已超过排行榜 #1** (affshoot 19.36)。这是唯一我们领先的竞争环境。策略: 维持, 不投入。

## 评估格式详解 (源码: liveweb-arena)

### 消息结构
```
System: "You are a web automation agent that interacts with real
        websites to complete tasks."
User: "[task description + current page accessibility tree]"
Assistant: "Let me think about this step...
{"action": {"type": "click", "params": {"element_id": 42}}}"
User: "[new page state after action]"
...重复直到任务完成或超时
```

### Action 格式
```json
{"action": {"type": "click|type|scroll|...", "params": {...}}}
```
- 嵌入在 assistant 消息中 (非 tool_calls)
- 支持 think tags (与 SWE-SYNTH 不同)
- 非标准 tool calling — 是 JSON-in-message 格式

### 评分算法
- 任务完成度 (binary 或 partial credit, 取决于任务)
- 在真实网站上执行操作序列
- 全员分数低且差距小 (16-28 分区间)

### Eval 参数
- Timeout: 7200s, Temperature: 0.7, Memory: 2GB
- Concurrency: **1** (串行)
- Docker image: `affinefoundation/liveweb-arena:latest` (外部拉取)
- 环境变量: TAOSTATS_API_KEY
- Max task ID: 107,000,000
- 不可本地 eval (task_id 范围限制, 需预定义任务集)

## 数据长度分析 (核心问题)

| 阈值 | 条数 | 比例 | 说明 |
|------|------|------|------|
| <8K chars (~2K tokens) | 0 | 0% | 完全没有短对话 |
| <16K chars (~4K tokens) | 18 | 4.2% | v1 用这 18 条 |
| <32K chars (~8K tokens) | 56 | 13.0% | seq=8192 也只能用 13% |
| <64K chars (~16K tokens) | 194 | 45.1% | 需要极大 seq_len |
| 全部 | 430 | 100% | 中位 ~70K chars (~18K tokens) |

**结论**: 即使 seq=8192 (~32K chars), 也只有 13% 数据可用。这是**结构性问题**, 不是数据量或质量问题。

### 为什么这么长?
- 每步发送完整 DOM accessibility tree (~11,600 chars/步)
- URL+title 不变时仍重发完整页面 (无去重)
- 旧步骤保留完整历史 (无压缩)
- Assistant 消息内容极短 (action 对象本身很小)
- 典型对话: 10-20 步 × 11,600 chars/步 = 116K-232K chars

## 短条目分析 (v1 使用的 18 条)

| 分数 | 条数 | 说明 |
|------|------|------|
| 1.00 | 4 | 完美完成 |
| 0.90 | 1 | 接近完美 |
| 0.75 | 1 | 较好 |
| 0.67 | 2 | 中等 |
| 0.50 | 10 | 半完成 |

大多是 5 条消息的短对话。质量参差 — 一半仅 0.50 分。
但作为安全网, 确保 LIVEWEB 非零即可。

## 瓶颈分析

| 瓶颈 | 影响 | 可解? | 解法 |
|------|------|------|------|
| 数据长度灾难 | 中位 145K chars, 无法训练 | 需上游改 | DOM 压缩 |
| 合成失败 | DashScope 全系列 0% 成功率 | 短期不可 | 等上游压缩后重试 |
| 全员弱 | 16-28 分, 差异极小 | — | 维持即可 |
| 非标准格式 | JSON-in-message, 非 tool_calls | 需上游改 | 标准化 |

## 数据行动方案

### v1: 安全网 (当前阶段 — 训练中)
- [x] 提取 18 条短条目 (<16K chars)
- [x] canonical 已替换为 18 条 (claudeuser-owned)
- 目的: 确保 LIVEWEB 非零分, 防止 GM 崩溃
- 预期: ~20-24 分 (与 v11 持平或略低)

### 中期: 不投入
- ROI 极低 (已领先, 且差距小)
- 保持 18 条作为覆盖
- 不生成新数据, 不做质量优化

### 长期: 上游改造 (需用户授权)

如果排行榜竞争加剧, 需要从 LIVEWEB 挤分:

| 改造 | 预期效果 | 位置 |
|------|---------|------|
| DOM 压缩 | 11,600→3,000-4,000 chars/步 (65% 压缩) | `liveweb-arena/env.py:1339` |
| 页面去重 | URL+title 不变时发 delta (50-70% 减少) | `liveweb_arena/core/browser.py:462-620` |
| 标准化 tool calling | JSON-in-message → OpenAI function calling | `liveweb_arena/core/agent_policy.py` |
| 添加 assistant 推理 | 当前 assistant 消息 ~0 chars, 加 1-2 句 | agent_policy.py |
| 历史步骤压缩 | 旧步骤只保留 action_type + result | env.py |

**预期综合效果**: 中位 tokens/entry 39K→8-10K, 可训练比例 4%→70%+

### 合成数据现状
- DashScope qwen3-max: 0% 成功率
- DashScope coder-plus: 0% 成功率
- DashScope 3.5-plus: 0% 成功率
- **结论**: 当前框架下 LLM 无法合成 LIVEWEB 数据, 只能用 DDB 真实数据

## 数据质量检查清单

- [x] `datasets.load_dataset('json', data_files=...)` 成功
- [x] Schema: `{"messages": [...], "env": "LIVEWEB", "score": float}`
- [x] 最后一条消息 role=assistant
- [x] 18 条短条目均 <16K chars
- [x] 所有条目有 assistant action JSON
- [ ] 上游压缩后重新验证格式 (长期)

## 准备文件

| 文件 | 位置 | 条数 | 状态 |
|------|------|------|------|
| canonical (短条目) | `data/canonical/liveweb.jsonl` | 18 | claudeuser-owned, v1 使用中 |
| 全量备份 | DDB | 15,844 | avg score 0.172 |
| 上游源码 | `../liveweb-arena/` | — | 只读参考 |
