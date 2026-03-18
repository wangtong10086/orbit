# LIVEWEB 数据计划与深度分析

> 最后更新: 2026-03-18 16:15 UTC | 优先级: P3 (结构性无解，仅维持) | 状态: v2 训练中

## 1. 环境概述

LIVEWEB 评估 LLM 作为 Web 自动化代理的能力。模型需要在真实网站上通过浏览器操作（click, type, scroll, goto 等）完成数据提取和任务执行。

**评分**: `correct_answers / total_answers`（LLM 验证答案正确性），平均值。
**格式**: 自由思考 + JSON action object（非标准 tool calling）。
**部署**: 需要 TAOSTATS_API_KEY，max task_id=107M，不可本地 eval。

**战略定位**: v11 ~24 分**已超过排行榜 #1** (affshoot 19.08)。唯一我们领先的环境。策略: 维持，不投入。

## 2. 当前数据状态

### 2.1 总体概况 (canonical: 18 条)

| 指标 | 值 |
|------|-----|
| 条数 | 18（短条目安全网） |
| 分数 | 0.50-1.00，平均 0.666 |
| 来源 | DDB 提取，无标注 |
| 平均长度 | 14,003 chars |
| 平均步数 | 2.6 步 |

### 2.2 Action 类型分布 (53 次 action)

| Action | 次数 | 占比 | 评估 |
|--------|------|------|------|
| goto | 25 | 47% | 跳转 URL |
| stop | 18 | 34% | 结束任务（每条 1 次） |
| wait | 5 | 9% | 等待页面加载 |
| view_more | 2 | 4% | 展开内容 |
| scroll | 2 | 4% | 滚动页面 |
| click | 1 | 2% | 点击元素 |
| type | 0 | 0% | **完全缺失** |
| type_role | 0 | 0% | **完全缺失** |
| click_role | 0 | 0% | **完全缺失** |
| press | 0 | 0% | **完全缺失** |

**严重问题**: 训练数据几乎只教 `goto + stop` 模式。`type`（搜索框输入）、`click_role`（按角色点击）等交互式操作完全没有。eval 中需要这些操作的任务必然失败。

### 2.3 步数分布

| 步数 | 条数 | 占比 |
|------|------|------|
| 2 步 | 15 | 83.3% |
| 3 步 | 2 | 11.1% |
| 10 步 | 1 | 5.6% |

**15/18 条是"goto 一个页面 → stop"的极简模式。** 模型学不到多步导航、条件判断、跨页面操作。

### 2.4 推理内容分析

- **69% 的 assistant 消息是纯 action JSON**，无任何推理
- 31% 含 `<think>` 标签，但标签内容**几乎为空**（平均仅 22 chars）
- **零有意义的 chain-of-thought 推理**

模型学到的是: 看到页面 → 直接输出 action，不需要思考。这在简单任务中有效，复杂任务中致命。

### 2.5 域名多样性

| 域名 | 条数 | 类型 |
|------|------|------|
| coingecko.com | 12 | 加密货币价格/交易量 |
| stooq.com | 7 | 股票/外汇数据 |
| taostats.io | 5 | Bittensor 子网数据 |
| news.ycombinator.com | 1 | 新闻聚合 |

**仅 3-4 个域名**，全部集中在金融/加密领域。模型对其他类型网站（电商、社交、新闻详情、表单填写）完全没有训练数据。

### 2.6 分数分布

| 分数 | 条数 | 含义 |
|------|------|------|
| 1.00 | 4 | 全部答案正确 |
| 0.90 | 1 | 接近完美 |
| 0.75 | 1 | 3/4 正确 |
| 0.67 | 2 | 2/3 正确 |
| 0.50 | 10 | **半数答案错误** |

**55% 的训练数据 (10/18) 只有一半答案正确。** 这意味着模型在学习部分错误的行为模式。

### 2.7 高分条目特征 (score≥0.9, 5 条)

共同点:
- 仅 2 步 (goto → stop)
- 简单任务: 2-3 个子问题，单页可回答
- 来源: CoinGecko 或 HackerNews
- 直接数据提取，无条件逻辑

**结论**: 高分 = 简单任务。数据无法教会复杂导航。

## 3. 瓶颈根因分析

### 3.1 结构性长度灾难

原始 430 条数据的长度分析:

| 阈值 | 可用条数 | 比例 |
|------|---------|------|
| <8K chars | 0 | 0% |
| <16K chars | 18 | 4.2% |
| <32K chars | 56 | 13.0% |
| 全部 | 430 | 100% |
| 中位长度 | ~70K chars (~18K tokens) | — |

**根因**: 每步发送完整 DOM accessibility tree (~11,600 chars)。URL/title 不变时仍重发。无历史压缩。

即使 seq=16384 (~64K chars)，也只有 45% 数据可用。这不是数据量问题，是**环境设计问题**。

### 3.2 Action 多样性危机

训练数据只覆盖 `goto + stop`。eval 任务可能需要:
- `type`: 在搜索框输入关键词
- `click`: 点击特定按钮/链接
- `click_role`: 按 ARIA role 点击
- `scroll`: 滚动到页面底部
- `press`: 键盘操作

这些操作 0% 训练覆盖 → eval 中相关任务必然失败。

### 3.3 零推理训练

模型学到"看页面 → 输出 action JSON"，无中间推理。对于需要:
- 比较多个选项
- 条件判断（如果 A 不存在则尝试 B）
- 多步规划

的任务，模型缺乏推理能力。

### 3.4 域名过拟合

仅 3 个金融域名。遇到未见过的网站（不同 DOM 结构、不同交互模式）时，模型大概率失败。

### 3.5 合成不可行

| 模型 | 成功率 |
|------|--------|
| DashScope qwen3-max | 0% |
| DashScope coder-plus | 0% |
| DashScope 3.5-plus | 0% |

LLM 无法在当前框架下完成浏览器任务。DDB 真实数据是唯一来源。

## 4. 行动计划

### v2 (当前): 安全网，不修改
- 18 条短条目
- 目的: 确保 LIVEWEB 非零
- 预期: ~20-24 分

### 不投入原因:
1. 我们已领先 #1 约 5 分
2. 全员分数低 (16-28)，差距小
3. 数据结构性问题无解（需上游改造）
4. ROI ≈ 0 (24→24 = 0 GM 提升)

### 长期: 上游改造 (需用户授权)

如果排行榜竞争加剧，需要从 LIVEWEB 挤分:

| 改造 | 位置 | 预期效果 |
|------|------|---------|
| DOM 压缩 | `liveweb-arena/env.py:1339` | 11,600→3-4K chars/步 |
| 页面去重 | `liveweb_arena/core/browser.py:462-620` | 50-70% 减少 |
| 标准化 tool calling | `liveweb_arena/core/agent_policy.py` | 统一格式 |
| Assistant 推理 | agent_policy.py | 增加 CoT |
| 历史压缩 | env.py | 旧步骤仅保留 action+result |

**综合效果**: 中位 tokens 39K→8-10K，可训练比例 4%→70%+。

### 如果上游改造完成:
1. 重新提取 DDB 数据（430+ 条变为可训练）
2. 确保 action 类型多样性（click, type, scroll 等）
3. 添加 CoT 推理到 assistant 消息
4. 目标: 覆盖 10+ 域名，5+ action 类型

## 5. 质量检查清单

- [x] Schema: `{"messages": [...], "env": "LIVEWEB", "score": float}`
- [x] 最后消息 role=assistant
- [x] 18 条均 <16K chars
- [x] assistant 含 action JSON
- [ ] Action 类型多样性 (当前仅 goto+stop)
- [ ] 域名多样性 (当前仅 3 个)
- [ ] 推理内容非空 (当前 69% 无推理)
- [ ] 高分条目比例 (当前 55% 仅 0.50)

## 6. 关键文件

| 文件 | 条数 | 状态 |
|------|------|------|
| `data/canonical/liveweb.jsonl` | 18 | v2 训练中 |
| DDB 全量 | 15,844 | avg score 0.172 |
| `../liveweb-arena/` | — | 上游源码参考 |
| `scripts/liveweb_gen.py` | — | 合成脚本（0% 成功率） |

## 7. 评分逻辑详解 (源码分析)

从 `scripts/liveweb_env_patched.py`:

```python
total_score = sum(v["score"] for v in answer_validations) / len(answer_validations)
```

每个任务包含多个子问题 (answer_validations)。每个子问题:
- LLM judge 比对模型答案与 ground truth
- 正确=1, 错误=0
- 总分 = 正确数 / 总数

失败模式 (score=0):
- `agent_timeout`: 模型超时
- `llm_error`: LLM judge 出错
- `cache_error`: 缓存问题
- `site_unreachable`: 网站不可达

**重要**: 即使模型正确导航到页面，如果提取的数据不准确（如读错数字、遗漏小数点），也会扣分。accuracy 比 navigation 更重要。
