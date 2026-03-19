# Training Knowledge

## Key Facts
- Base model: Qwen/Qwen3-32B (always train from base, not from other fine-tunes)
- Pre-quantized: unsloth/Qwen3-32B-bnb-4bit (18GB vs 65GB, ~90s download)
- Method: QLoRA (4-bit NF4)
- Training from top model (#2) failed: loss oscillated wildly (0.6→0.9), QLoRA cannot stably learn on deeply-tuned models
- SFT 1 epoch is sufficient; 2+ epochs risk overfitting on small datasets

## Current Best Config (v7-v12)

| Param | Value | Notes |
|-------|-------|-------|
| lr | **1e-4** | 1e-5 too low (v1-v3 plateau), 5e-5 regressed (v6) |
| LoRA r | **64** | r=16 insufficient, r=128 marginal benefit |
| LoRA alpha | **128** | 2x rank |
| epochs | **1** | 3 epochs on 4528 samples → catastrophic forgetting |
| seq_len | **8192** | SWE-SYNTH needs it; GAME unaffected (v12 confirmed) |
| batch | **2** | |
| grad_accum | **8** | effective batch 16 |
| packing | **True** | 2-3x efficiency; Unsloth latest fixes cross-sequence contamination |
| warmup | **3%** | |
| max_grad_norm | **0.3** | |

## Loss Convergence
- Initial: ~0.67-0.86 (step 10)
- Rapid drop: ~0.3 by step 50
- Plateau: 0.11-0.20 (more envs → higher final loss)
- Abnormal: >0.5 after step 50 → terminate immediately
- v8 (4 envs): 0.11 | v9 (6 envs): 0.14 | v10 (7 envs): 0.19

## Sequence Length
- seq=4096: default, works for GAME/NAVWORLD/LIVEWEB
- seq=8192: needed for SWE-SYNTH (98% truncated at 4096 → 37% at 8192)
- v12 confirmed: seq=8192 works, GAME score unaffected
- Trade-offs: ~80s/step (vs ~48s), loss ~0.21 (vs ~0.17), ~82GB VRAM

## Training Speed
- Single H200 at seq=8192: ~88-92s/step
- 4x H200 DDP at seq=4096: ~46s/step
- Typical run: 230-440 steps, 6-14 hours at seq=8192

## Historical Best (old repo, for reference)
- v10: 7 envs, 13733 entries, loss ~0.19, GAME=22.0, NAVWORLD=5.1
- v11: 7 envs, 15273 entries, loss ~0.17, GAME=22.6, NAVWORLD=5.7
- v12: 7 envs, 15367 entries, seq=8192, loss ~0.21, GAME=22.0 (partial eval)
- Total old repo cost: ~$200

## Packing Safety
- Latest Unsloth fixes cross-sequence contamination via position IDs
- Supports FA2, FA3, xFormers, SDPA backends
- v1/v2 FA2 warnings may be from older Unsloth; safe with latest version

## Tool Calling (NAVWORLD critical)
- Training: `tokenizer.apply_chat_template(messages, tools=tools)` → Qwen3 native format
- Inference: sglang with `--tool-call-parser qwen25`
- Both required — without either, NAVWORLD scores 0
- v8 breakthrough: 0% → 33% non-zero when both fixes applied
- **Known sglang bugs with qwen25 parser**:
  - Issue #9184: tool_call tags leak into content field instead of tool_calls
  - Issue #8331: qwen3 parser too eager — greedy regex interferes with custom formats
  - Issue #7769: qwen25 parser doesn't work for Qwen3-30B-A3B
- **Fallback order**: qwen25 → hermes → Qwen-Agent built-in parser
- **Qwen team's own recommendation**: use Qwen-Agent's built-in tool call parser rather than vLLM/SGLang auto-tool-choice parsers

## DPO Pipeline (built, unused)
- 2688 preference pairs: GAME 589, LGC-v2 800, NAVWORLD 241, PRINT 800, SWE-SYNTH 258
- Config: beta=0.1, lr=5e-6, batch=1, grad_accum=8
- CLI: `forge train dpo-launch`

## Phase 3+ Methods (research, 2026-03-18)

### Method Selection
| Env | Recommended | Rationale | Fallback |
|-----|------------|-----------|----------|
| GAME | **GRPO** | Win/loss = verifiable reward; DeepResearch/QwQ/DeepSeek-R1 all chose GRPO | DPO (589 pairs) |
| NAVWORLD | **GRPO** | Tool-call correctness = verifiable reward | DPO (241 pairs) |
| SWE-SYNTH | **RLVR** | Binary pass/fail = natural verifiable reward | DAPO (long seq stability) |
| LIVEWEB | Hold | Data too long, needs upstream compression | — |

### GRPO (Group Relative Policy Optimization) — preferred
- Eliminates critic model; samples multiple responses, normalizes reward within group
- Stronger than DPO: generates new responses during training (not limited to static pairs)
- Industry consensus: DeepResearch + QwQ + DeepSeek-R1 all chose GRPO

### RC-GRPO (Reward-Conditioned GRPO) — Feb 2026, DIRECTLY RELEVANT
- Paper: "Reward-Conditioned Group Relative Policy Optimization for Multi-Turn Tool Calling Agents" (arxiv 2602.03025)
- **Solves vanilla GRPO's core problem**: in multi-turn tool calling, rewards are sparse and within-group variance collapses (all 0 or all 1), making group-normalized advantage uninformative
- Result: Qwen2.5-7B achieves 85% accuracy on BFCLv4, beating all closed-source APIs including Opus-4.5 (61.25%)
- **Directly applicable to NAVWORLD (multi-turn tool calling) and GAME (sparse win/loss rewards)**
- Hardware: 8x H200 GPUs (we have 4x H200)

#### RC-GRPO Two-Stage Pipeline

**Stage 1: RCTP (Reward-Conditioned Trajectory Policy) — SFT**
- Data: 1:1 ratio expert (R=1) + failure (R=0) trajectories (paper uses 800:800 = 1600 total)
- Reward token is **literal text** appended to first user message: `[Reward Goal: <|high_reward|>]` or `[Reward Goal: <|low_reward|>]`
- Standard cross-entropy SFT loss on assistant tokens
- Output: reference policy that generates varied-quality trajectories conditioned on reward token

**Stage 2: RC-GRPO — RL**
- Initialize from Stage 1 policy
- Per prompt: sample G trajectories with diverse reward tokens (p=0.5 high/low mix)
- Binary trajectory-level reward: R(tau) = R_state * R_action (both must be 1)
- Group-normalized advantage: A_j = (R_j - mu_g) / (sigma_g + eps)
- PPO-style clipped objective + KL regularization against Stage 1 ref policy
- Key insight: reward conditioning guarantees within-group variance, preventing collapse

#### RC-GRPO Data Format Requirements (for Data Agent)

**Stage 1 data format** (OpenAI chat format with reward token):
```json
{
  "task_id": "navworld_task_1",
  "messages": [
    {"role": "user", "content": "Find restaurants near Beijing Station\n[Reward Goal: <|high_reward|>]"},
    {"role": "assistant", "content": "", "tool_calls": [{"name": "search_poi", "arguments": {...}}]},
    {"role": "tool", "content": "{\"results\": [...]}"},
    {"role": "assistant", "content": "I found 3 restaurants..."}
  ],
  "reward": 1
}
```

**Stage 2 needs**: prompts only (model generates own trajectories) + reward function returning binary 0/1
- Reward = R_state (final state matches golden) * R_action (all required tool calls present with correct params)
- For GAME: R = win/loss (already binary)
- For NAVWORLD: R = correct tool-call sequence + valid final answer

**Data preparation checklist for Phase 3**:
1. Collect 800+ expert trajectories per env (from eval successes or distillation)
2. Collect 800+ failure trajectories per env (from model rollouts on same tasks)
3. Tag each with reward token in first user message
4. Build per-env reward function (binary: state match * action match)
5. Prepare prompt-only dataset for Stage 2 (task descriptions without trajectories)

#### RC-GRPO Key Ablation Findings
- RCTP init is essential: SFT + RC-GRPO gives negligible gains vs RCTP + RC-GRPO (+38.75%)
- Reward conditioning in GRPO matters: RCTP + RC-GRPO beats RCTP + vanilla GRPO (+11.25%)
- No official code repo; third-party `jackefn/rco-grpo` implements a different variant
- Hyperparams (from related impl): group_size=8, kl_ctl=0.04, lr=1e-6

### OpenPipe ART (Agent Reinforcement Trainer) — open source
- Framework for training multi-step agents using GRPO
- Supports Qwen2.5, Qwen3, Qwen3.5, Llama
- Handles complex trajectories including tool calls and sub-agent calls
- RULER feature for automatic reward generation
- Could be our Phase 3 infrastructure (vs building from scratch)
- Source: https://github.com/OpenPipe/ART

### RLVR (Reinforcement Learning with Verifiable Rewards)
- Auto-verification (unit tests, math checks) replaces human preference labels
- Perfect match for SWE-SYNTH binary scoring
- DeepSeek-R1 proved pure RLVR can produce emergent reasoning
- Key finding: most RLVR gains are "search compression" (pass@k to pass@1), minority is true capability expansion

### Key Insights from DeepResearch
- "Data/environment stability matters more than RL algorithm choice"
- Rejection sampling: generate many trajectories, keep only high-quality diverse ones
- Dynamic difficulty filtering: drop tasks model always passes/fails, keep medium difficulty
- Pure 0/1 reward works (no format reward needed)
- Action-level penalties prevent reward hacking (e.g. penalize "no action" or "invalid tool call")

### SFT Plateau Triggers (when to switch methods)
- 2x data yields <15% improvement → DPO/GRPO
- Structural zero: 0% across 3+ versions → SFT-unlearnable, try RL or drop
- Rank stagnation for 3+ versions → method change required
