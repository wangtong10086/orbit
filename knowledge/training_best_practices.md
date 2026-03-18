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

相关研究:
- DeepResearcher (2504.03160): 首个端到端deep research agent RL训练框架
- Search-R1 (2602.19526): prompt/reward/policy三维优化deep research agent
- Step-DeepResearch (2512.20491): Agentic CPT→SFT→RL + Checklist-style Judger reward

Sources:
- [Tongyi DeepResearch Technical Report](https://arxiv.org/abs/2510.24701)
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
