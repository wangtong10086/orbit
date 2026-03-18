# Training Best Practices (2026)

**Last updated**: 2026-03-18 (Strategist research)

## Qwen3 QLoRA Fine-tuning

### Unsloth Packing (CRITICAL)
- **最新版Unsloth已修复packing跨序列污染问题** — 使用position IDs标记序列边界
- 支持所有attention后端: FA2, FA3, xFormers, SDPA
- 自动启用，无需手动配置
- **v1/v2的FA2 warning可能来自旧版Unsloth** — 如果Unsloth是最新版，packing是安全的
- Source: [Unsloth Packing Docs](https://unsloth.ai/docs/new/3x-faster-training-packing)

### LoRA 配置
- 保守默认: r=16, α=32
- 我们用: r=64, α=128 (更激进，但专项fine-tuning可能需要更高rank)
- 建议: 如果v2效果不好，尝试降到r=32, α=64

### 数据配比
- Qwen3推荐: **75%推理 + 25%非推理** 保持基础能力
- 我们的数据: GAME(43%) + NAVWORLD(40%) + SWE-SYNTH(17%) + LIVEWEB(0.3%)
- GAME和SWE-SYNTH偏推理，NAVWORLD偏tool-calling → 配比大致合理

### KL-Anchored SFT
- 在SFT中加入KL散度惩罚，使adapter学习格式/风格的同时保持接近base model
- 防止通用能力退化
- 我们目前没有用 — **如果v2出现能力退化，考虑添加KL约束**

## Qwen3 Tool Calling (⚠️ CRITICAL)

### sglang tool-call-parser 问题
- **`--tool-call-parser qwen25` 对Qwen3可能不可靠**
- GitHub issue #7769: Qwen3-30B-A3B 用 qwen25 parser "not work as expect"
- vLLM用 `--tool-call-parser hermes` 对Qwen3有效
- 但我们的历史记录显示 qwen25 在Qwen3-32B上**曾经有效**（v8: NAVWORLD 0%→33%）
- **风险**: 如果v2 NAVWORLD=0，第一步检查parser。尝试 `hermes` 或 `qwen3_xml`
- Source: [sglang issue #7769](https://github.com/sgl-project/sglang/issues/7769)

### 正确的tool calling流程
1. 训练: `tokenizer.apply_chat_template(messages, tools=tools)` → Qwen3原生格式
2. 推理: sglang加 `--tool-call-parser qwen25` (已验证) 或 `hermes` (vLLM推荐)
3. **两步缺一不可** — 历史教训: v3-v7 NAVWORLD全是0分

## Post-Training 2026 (Phase 3+ 方法论)

### 行业验证: Qwen DeepResearch 训练范式 (2025-2026)

阿里通义DeepResearch证明了**SFT→RL三阶段pipeline**的有效性:

1. **Agentic CPT（持续预训练）** — base model注入agent行为inductive bias
   - 两阶段: 32K→128K上下文渐进扩展
   - 全自动数据合成pipeline，不依赖人工标注
2. **Agentic SFT** — 用专家级搜索-推理轨迹cold start基本能力
3. **Agentic RL** — GRPO在真实web环境中做on-policy强化学习
   - 奖励: F1 score对比ground truth
   - 关键: **真实环境交互 >> RAG模拟环境**

模型: Qwen3-30B-A3B (MoE, 30.5B total / 3.3B active per token)

**对我们的核心启示**:
- **SFT是正确的第一步** — DeepResearch也从SFT cold start开始
- **GRPO优于DPO** — DeepResearch和QwQ都选择GRPO而非DPO
- **真实环境RL关键** — 我们的GAME/NAVWORLD有真实eval环境，可做on-policy RL
- **Agentic CPT不适用** — 需要巨量计算资源，我们用QLoRA SFT+RL即可

### DeepResearch 数据合成方法深度分析

#### 核心理念: "数据和训练环境的稳定性比RL算法本身更关键"

#### 1. Entity-Anchored Knowledge Memory（实体锚定知识库）
- 将多源数据（网页爬取、知识图谱、历史agent轨迹）重构为**实体为中心的结构化表示**
- 随机采样实体及其关联知识 → 生成多风格QA对
- **可借鉴**: 我们的GAME数据可按game type构建"策略知识图谱"，NAVWORLD可按POI类型构建实体库

#### 2. WebSailor/WebShaper — 可控难度合成
- **WebSailor**: 知识图谱随机游走 → 生成QA数据集（图结构保证多跳推理）
- **WebShaper**: 集合论形式化建模 + **原子操作**控制难度
  - 原子操作: 实体合并、属性隐藏、关系模糊化 → 系统性增加复杂度
  - 迭代升级: 一轮输出 → 变成下一轮更复杂的输入（PhD级问题生成）
- **可借鉴**: GAME数据合成可用类似方法 — 从简单博弈场景开始，逐步增加对手策略复杂度

#### 3. CPT阶段: 4类Action合成
- **Planning**: 开源模型分解问题 + rejection sampling（基于实体一致性）
- **Reasoning**: 两阶段推理链生成 + **双重过滤**（推理长度 + 答案一致性）
- **Decision-Making**: 显式建模选择点，探索可行动作空间 → 重构为多步决策序列
- **Function-Calling**: 异构模拟环境扩展工具调用多样性
- **可借鉴**: NAVWORLD数据可用Decision-Making方法 — 在导航选择点生成多个候选动作

#### 4. SFT阶段: Rejection Sampling协议
- 高性能开源模型生成轨迹 → **严格rejection sampling**保留高质量多样模式
- 基于ReAct框架（丰富推理行为）+ IterResearch框架（长程任务规划能力）
- **20%+ SFT样本超过32K tokens，10+次工具调用**
- **可借鉴**: 我们可以用Qwen3-32B自身生成GAME/NAVWORLD轨迹 → rejection sampling留精品

#### 5. RL阶段: 数据筛选与稳定性
- **动态难度过滤**: 自动剔除模型"总是失败"或"总是成功"的问题 → 只保留中等难度
- **Negative sample保守策略**: 排除因长度限制而未完成的轨迹 → 防止format collapse
- **定期刷新训练集**: 随policy改进，后台进程持续发现新挑战性问题
- **纯0/1奖励**: 答案正确=1，错误=0（无format reward）
- **可借鉴**: GAME环境天然适合 — 胜=1/负=0，自动过滤太简单/太难的对局

#### 6. Search-R1补充发现: Reward设计细节
- **F1 reward不如EM (Exact Match)** — F1导致"答案回避"（模型学会不给答案以避免扣分）
- **F1+ reward**: `R = R_F1 - 0.1×I[无搜索] - 0.1×I[无回答]` — 加入action-level惩罚解决回避
- **REINFORCE > PPO > GRPO** (Search-R1发现) — 但DeepResearch选GRPO且成功，说明**环境和数据比算法选择更重要**
- **可借鉴**: 我们的reward设计需要加入action-level约束，不能只看最终胜负

#### 7. DeepResearcher: 80K样本 + 污染检测
- 训练数据: NQ:TQ:HotpotQA:2Wiki = 1:1:3:3（80K总量，75%多跳）
- **污染检测**: 每个问题用base model采样10次(pass@10)，如果已知答案 → 剔除
- **低质量过滤**: 剔除时效性问题、主观问题、有害内容
- **可借鉴**: 用base Qwen3-32B对我们的训练数据做pass@10，剔除已知答案（防止过拟合）

### 对我们各环境的具体借鉴

| 技术 | GAME | NAVWORLD | SWE-SYNTH |
|------|------|----------|-----------|
| **Rejection sampling** | ✅ 用Qwen3生成多局 → 只保留展示好策略的 | ✅ 生成多条导航轨迹 → 只保留最优路径 | ✅ 生成多个解法 → 只保留通过测试的 |
| **难度过滤** | ✅ 剔除太简单(random也能赢)和太难(总是输)的 | ⚠️ 需要定义"难度" | ✅ 剔除base model已能解决的 |
| **污染检测(pass@10)** | ✅ 有价值 — 防止训练在已知博弈上过拟合 | ❌ 不适用 — 每次导航不同 | ✅ 有价值 — 剔除trivial bug |
| **Action-level reward** | ✅ 不只看胜负，加入"合法出牌率"惩罚 | ✅ 加入"有效tool-call率"惩罚 | ⚠️ 复杂 |
| **动态训练集刷新** | ✅ Phase 3 RL时持续生成新对局 | ❌ 数据来源固定 | ❌ 数据来源固定 |
| **实体锚定知识库** | ✅ 按game type建策略库 | ✅ 按POI类型建导航模板 | ❌ 不适用 |

### 立即可行动项（Phase 2后）

1. **GAME rejection sampling** — 用当前v2 model生成1000局 → 只保留展示学到策略的轨迹 → 合入v3
2. **GAME难度过滤** — 用base Qwen3-32B跑pass@10 → 剔除base model已能赢的场景
3. **NAVWORLD rejection sampling** — 用v2 model生成导航轨迹 → 保留tool-call正确率>80%的
4. **RL reward加入action-level惩罚** — 不只看最终胜负/分数，还惩罚"不行动"和"无效工具调用"

Sources:
- [Tongyi DeepResearch Technical Report](https://arxiv.org/abs/2510.24701)
- [Tongyi DeepResearch Blog](https://tongyi-agent.github.io/blog/introducing-tongyi-deep-research/)
- [Tongyi DeepResearch GitHub (开源)](https://github.com/Alibaba-NLP/DeepResearch)
- [DeepResearcher: Scaling Deep Research via RL](https://arxiv.org/abs/2504.03160)
- [Search-R1: How to Train Your Deep Research Agent](https://arxiv.org/abs/2602.19526)

### GRPO (Group Relative Policy Optimization) — **Phase 3首选**
- 消除critic model，采样多个response后组内归一化reward
- 比DPO更强: DPO受限于静态偏好对质量，GRPO在训练中生成新response
- **DeepResearch + QwQ + DeepSeek-R1都选择GRPO** — 行业共识
- **适合我们的GAME环境** — 胜负明确，reward自动验证
- **适合NAVWORLD** — tool-call正确率可作为verifiable reward
- Source: [Post-Training 2026](https://llm-stats.com/blog/research/post-training-techniques-2026)

### DAPO (Dynamic Alignment with Policy Optimization)
- ByteDance/清华，解决长CoT训练不稳定
- 4个关键机制: Clip-Higher, Dynamic Sampling, Token-level PG Loss, Overlong Reward Shaping
- **在AIME 2024上用Qwen2.5-32B达到50分，比DeepSeek-R1-Zero少50%步数**
- **适合SWE-SYNTH** — 长多轮对话推理

### RLVR (Reinforcement Learning with Verifiable Rewards)
- 用自动验证(单元测试、数学验证)替代人类偏好标签
- **完美匹配SWE-SYNTH** — 二值评分(pass/fail)天然是verifiable reward
- DeepSeek-R1证明纯RLVR可以产生涌现推理能力

### RLFactory
- 多轮tool-use RL框架
- Qwen3-4B在NQ上实现6.8x吞吐提升
- **适合NAVWORLD** — multi-turn tool calling

### Phase 3+ 方法选择建议 (更新: 基于DeepResearch研究)
| 环境 | 推荐方法 | 原因 | 备选 |
|------|---------|------|------|
| GAME | **GRPO** | 胜负reward自动验证，行业验证 | DPO (如GRPO infra不就绪) |
| NAVWORLD | **GRPO→RLFactory** | tool-call正确率=verifiable reward，DeepResearch验证 | DPO (241对快速突破) |
| SWE-SYNTH | RLVR | pass/fail评分天然verifiable | DAPO (长序列稳定性) |
| LIVEWEB | Hold | 数据不够，等上游压缩 | — |

**⚠️ Phase 3方法变更**: NAVWORLD从"DPO优先"改为"GRPO优先"。理由: (1) DeepResearch/QwQ/DeepSeek-R1三大项目均选择GRPO; (2) NAVWORLD的tool-call正确率天然是verifiable reward，无需人工偏好标注; (3) DPO保留为备选（如GRPO框架搭建耗时过长）。

## Affine Subnet 机制

- **Winners-take-all**: Pareto frontier model获得最多incentive
- **Copy-proof**: 新矿工必须明显超越(not just match)才能通过anti-copy filter
- **Pareto frontier**: 需要在所有环境上都不被其他矿工dominate
- 意味着: 均衡发展比单项突出更重要（与我们的GM策略一致）
