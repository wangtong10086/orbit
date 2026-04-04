# GAME Environment

> Status: Reference note
> Authority: Non-normative
> Last reviewed: 2026-04-04
> Use this file for background and deep analysis, not as the primary source of truth.


## Key Facts
- 7 active games, eval uses OpenSpiel + MCTS opponent (except goofspiel: simultaneous → random)
- `strip_think_tags=True` — think blocks stripped before action parsing, but model should still think
- Scoring: normalized from game utility range to [0,1]
- Config variants per game: board sizes (5/7/9/11 for hex), card counts, etc.
- System prompt instructs model to think in `<think>` tags then output action ID

## Current Collection Policy

当前 `GAME` 的数据收集已经把 collector 和 trajectory generator 拆开。

当前默认策略：

- collector: [forge/data/game_gen.py](/home/wangtong/affine-swarm/forge/data/game_gen.py)
- generator registry: [forge/data/game_trajectory_generators.py](/home/wangtong/affine-swarm/forge/data/game_trajectory_generators.py)
- search generators: [forge/data/game_generators/search_generators.py](/home/wangtong/affine-swarm/forge/data/game_generators/search_generators.py)
- exact policy generators: [forge/data/game_generators/policy_generators.py](/home/wangtong/affine-swarm/forge/data/game_generators/policy_generators.py)
- policy-model generators: [forge/data/game_generators/model_generators.py](/home/wangtong/affine-swarm/forge/data/game_generators/model_generators.py)

当前默认 generator 不是 `random`，而是按游戏选择真实 family：

- `othello / hex / clobber`
  - bounded-budget search
  - 同时支持 `--generator-source policy_model`
- `goofspiel / leduc_poker / liars_dice / gin_rummy`
  - offline policy snapshot

额外采样路径：

- `--generator-source policy_model`
  - 使用 self-play 训练好的 per-game policy/value 模型

当前真实验证状态：

- `leduc_poker`
  - self-play 训练、teacher eval、policy-model sampling 已在 rental 上真实跑通
- `goofspiel`
  - self-play 训练和 policy-model sampling 已跑通
- `liars_dice / gin_rummy`
  - self-play 训练已能启动并落 checkpoint
  - 长时间 teacher gate 还未完成
- `othello`
  - 已支持 perfect-info self-play
  - board-plane featurizer + residual CNN + tree PUCT 已接入
  - 本地最小 self-play smoke 和 `policy_model` 采样已通过
- `hex / clobber`
  - 已接入和 `othello` 相同的 perfect-info self-play 主路径
  - 当前仍待更长时间的 rental gate 验证

## Policy Model Training

当前 `GAME` 的 `policy_model` 训练逻辑已经按游戏分型：

- `othello / hex / clobber`
  - perfect-info self-play
  - board-plane featurizer
  - residual CNN / ResNet
  - tree PUCT
  - teacher gate 目标 `>= 90% / 200`
- `leduc_poker / goofspiel / liars_dice / gin_rummy`
  - AlphaZero-inspired imperfect-information self-play
  - residual MLP policy-value model
  - root search + replay + arena eval
  - teacher 只作为 baseline / gate 对手，不再作为训练数据来源

当前训练运行方式：

- 7 个游戏独立训练进程
- 单游戏内部 replay 生成已支持并行 worker
- perfect-info 三个游戏的 replay evaluator 已迁到各自进程的 `cuda`
- imperfect-info 四个游戏目前 replay evaluator 仍主要走 CPU

更完整的训练逻辑和当前参数见 [docs/game-generators.md](/home/wangtong/affine-swarm/docs/game-generators.md)。

扩展方式和模块边界见 [docs/game-generators.md](/home/wangtong/affine-swarm/docs/game-generators.md)。

## Active Games + Bot Strategy (2026-03-23)

| idx | Game | Opp MCTS | Bot | Win Rate | Strategy |
|-----|------|---------|-----|----------|----------|
| 0 | goofspiel | random | Rule v4 | 95% | 比例出价+终局调整 |
| 1 | liars_dice | 3000sim/200r | MCTS 10000sim | 80% | 固定决策框架: hand→概率→decision |
| 2 | leduc_poker | 3000sim/200r | Rule v4 | 60% | 决策表+pot odds+对手range |
| 3 | gin_rummy | 500sim/10r | MCTS 2000sim | 80% | deadwood/meld/knock timing |
| 4 | othello | 1000sim/20r | MCTS 3000sim | 67% | 9条规则(corner/chain/X-sq/mobility/compact/parity) |
| 6 | hex | 1000sim/50r | MCTS 3000sim | 60% | bridge/double threat/chain/ladder/acute corner |
| 7 | clobber | 1500sim/100r | MCTS 5000sim | 80% | safe capture/fragment/chain/mobility/parity |

## Think Chain Design Principles

All thinks use **IF-THEN rule patterns** that SFT can learn:
- `Rule: TAKE CORNER. a1 is available → corners never flip → take it`
- `Rule: SAFE CAPTURE. No adjacent opponent → can't be recaptured → safe`
- `Step 1: hand analysis → Step 2: probability → Step 3: decision`

NOT vague descriptions like "this is a good move because search says so."

## v12 Data — CURRENT (2026-03-27, on HF)

**Strategy**: NO think blocks. Top miner tested (2026-03-27): outputs pure numbers with real eval prompts. Think blocks only appear with short/unfamiliar prompts (base model fallback, not trained behavior). Top miner uses **full fine-tune** (not LoRA).
**File**: `data/canonical/game.jsonl` → HF `monokoco/affine-sft-data`

### v13 GAME Distribution (17,244 total, on HF)

| Game | Entries | % | Quality Gate | Status |
|------|---------|---|-------------|--------|
| goofspiel | 2,000 | 11.6% | — | ✅ |
| leduc_poker | 2,247 | 13.0% | fold 4.0% (247 augmented) | ✅ |
| liars_dice | 3,351 | 19.4% | call-first 13.0% | ✅ |
| gin_rummy | 1,026 | 5.9% | knock 95% (v8 data, think stripped) | ✅ |
| hex | 2,106 | 12.2% | 5/7/9/11 boards balanced | ⚠️ need more |
| othello | 1,321 | 7.7% | — | ⚠️ need more |
| clobber | 5,193 | 30.1% | — | ⚠️ need more |

### Full Training Mix

| Env | Entries | % |
|-----|---------|---|
| GAME | 17,244 | 53.1% |
| LIVEWEB | 9,999 | 30.8% |
| NAVWORLD | 4,240 | 13.1% |
| SWE-I | 1,037 | 3.3% | 50 MB |

### Known Data Issues (need pyspiel to fix)

1. **gin_rummy**: only 604 entries (v8 had 1026), only 55.8% games knock (v8=95%). Need more data + bot that knocks more.
2. **leduc_poker**: 0% fold actions. Bot never folds. Need fold examples for J vs raise.
3. **spatial games (hex/oth/clob)**: 0% but NOT SFT ceiling — top miner proves SFT can learn spatial games. Issue is data quality + training method (LoRA vs full fine-tune).

### Top Miner Analysis (2026-03-27)
Model: `papyrus-puppy/affine-5Dt8TFLaL7ZQQBds6eLMz6kfBFG8h36S7FZFory5ALTigtqD`
- **Full fine-tune** Qwen3-32B (14 safetensors, no LoRA adapter)
- No think blocks in eval (pure action numbers)
- Strategy quality: corner-aware (othello), hand-sensitive (liars_dice), path-connected (hex)
- Likely trained with strong MCTS bot + large data + full fine-tune
- **Key gap vs us**: full fine-tune vs LoRA r=64

### Regeneration Priority (need pyspiel)
1. **gin_rummy** — 604→1000+ entries, bot must knock 95%+ of games (v8 had 95%, v12 only 55.8%)
2. **leduc_poker** — add fold logic (J vs raise → fold). Currently 0% fold in data.
3. **spatial games** — need better data quality (corner rules, path strategy) + consider full fine-tune.

### Lessons Learned (do NOT repeat)
- v7: reduced liars_dice 1829→1000. Caused regression. **Never reduce total count without replacement.**
- v2.20: liars_dice 0% — bid/call imbalance (34.9% call vs 65.1% bid). Model over-learned bidding.
- v2.23: spatial games 0% with 4x data. Volume alone doesn't help — quality/format must change.
- v2.23: model does NOT generate think blocks (0% think rate). System prompt conflict needs resolution.
- Canonical has 64 "unknown" game entries — must clean these out in v9.
- **v2.25: liars_dice 0% — call-first rate 41.7% (v8 was 13.4%). Model learned "call immediately".** Root cause: generate_v11.py bot_player=1 at 70% + over-aggressive call logic. Fix: balanced P0/P1 + conservative call threshold. v12 rebalanced to 13% call-first.
- **v2.25: gin_rummy knock rate 0% in eval** — training data has only 2.3% knock actions (55). Model never learns to knock. Need ≥10% knock rate in data.
- **v2.25: leduc_poker 0% fold in eval** — training data has 0% fold actions. Model became over-passive (78% call vs 22% raise). Need fold examples (~10%) to teach when to fold weak hands.
- **v2.25 eval had 20/100 infrastructure errors** (connection failures) counted as 0 score, inflating the GAME score penalty.

## Tools

| File | Purpose |
|------|---------|
| `scripts/game/mcts_helper.py` | Shared MCTS bot factory (configurable sim count) |
| `scripts/game/{game}_bot.py` | Per-game MCTS bot + rule-based think generator |
| `scripts/game/generate_fast.py` | Data generation: bot vs random |
| `scripts/game/test3.py` | Bot testing: bot vs MCTS (eval conditions) |
| `scripts/game/test_bots.sh` | Upload/test/status/analyze wrapper |
