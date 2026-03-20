# GAME Environment

## Key Facts
- Scheduling weight 3.0 (sampled 3x more often by validators — more data points, NOT 3x scoring weight)
- Scoring uses geometric mean across all environments equally — no per-env weight multiplier
- Multi-turn gameplay, assistant replies are often single digits (action IDs)
- Eval uses OpenSpiel framework, **7 games active** (not all 22)
- `strip_think_tags=True` in eval — think blocks are auto-stripped
- 2 retry mechanism: model gets a second chance on parse errors
- Scoring: win/loss/draw per game, averaged across samples
- Leaderboard top scores: ~45-65 points

## Active Games (eval 实际评估范围)

Source: `affine-cortex/affine/database/system_config.json`
dataset_range: `[[0, 500000000], [600000000, 800000000]]`

| idx | Game | task_id range | Status |
|-----|------|--------------|--------|
| 0 | **goofspiel** | 0-99M | ✅ Solved (100% win) |
| 1 | **liars_dice** | 100M-199M | ✅ Zero (SFT-unlearnable) |
| 2 | **leduc_poker** | 200M-299M | ✅ Strong |
| 3 | **gin_rummy** | 300M-399M | ✅ Bot-improved |
| 4 | **othello** | 400M-499M | ✅ Zero (SFT-unlearnable) |
| 5 | backgammon | 500M-599M | ❌ excluded from eval |
| 6 | **hex** | 600M-699M | ✅ Zero (SFT-unlearnable) |
| 7 | **clobber** | 700M-799M | ✅ Zero (SFT-unlearnable) |
| 8+ | hearts, euchre, dots_and_boxes, go, chess, checkers, quoridor, blackjack, phantom_ttt, 2048, solitaire, bridge, amazons, oware | 800M+ | ❌ not in eval range |

**只有 idx 0-4 和 6-7 会被评估。** 其余游戏的训练数据是浪费。

## Format Requirements
- System prompt tells model to respond with action ID
- Assistant reply: pure integer (action ID) or think block + integer
- Eval parser extracts the number; anything else = parse error

## Data Status (2026-03-20)

### Canonical: 2794 entries (v4 rebuild + seq=16k filter)
| Game | Count | % | Learnability | Bot Win Rate |
|------|-------|---|-------------|-------------|
| goofspiel | 1122 | 40.2% | Solved | 98% |
| gin_rummy | 834 | 29.8% | Bot-improved | 97% |
| leduc_poker | 488 | 17.5% | Strong | 59% |
| liars_dice | 245 | 8.8% | Needs testing (bot fixed) | 97% |
| hex | 50 | 1.8% | Testing (bot 55% win) | 55% |
| clobber | 50 | 1.8% | Testing (bot 59% win) | 59% |
| othello | 5 | 0.2% | Testing (bot 79% win) | 79% |

- Learnable core (goofspiel + leduc + gin_rummy): **2444 (87.5%)**
- "Unlearnable" (need more data): 350 (12.5%)
- 100% think blocks, 0% Chinese, all English

### v4 Quality Improvements (2026-03-20)
- **1026 Chinese think entries** → translated to English via GPT-5.4
- **545 no-think entries** → removed
- **14351 template thinks** → regenerated with diverse strategic reasoning
- **liars_dice bot dice parse bug** → fixed (was showing empty `[]`)
- **gin_rummy think diversity** → 1.4% → 87% unique
- **Downsampled zero-tier** → 658→155 (focused on quality)

### Pending: v4 Batch 2 (1165 entries)
File: `data/game_bot_v4_batch2.jsonl`
- leduc_poker +291, gin_rummy +487, othello +158, hex +111, clobber +118
- Sent to Data Agent for merge

## Bot Strategy Pipeline
- pyspiel installed via `.pylibs/`
- Bots: `scripts/game_bots.py` — all 7 active games implemented
- Generator: `scripts/game_bot_gen.py` — plays bot vs random, records winning trajectories
- Quality tools: `scripts/game_data_clean.py` (audit/clean), `scripts/game_think_regen.py` (think regen via LLM)
- Can regenerate unlimited data for any game

## Evaluation Setup
- `--concurrency 4 --timeout 7200` (old 600s timeout missed long games)
- Temperature: 0.7, Memory: 2GB
- Docker image: openspiel:eval
- v9 mean jumped 0.10→0.19 just from timeout fix

## Current Best / Status
- v11: mean=0.226, 39% non-zero, 100 samples (~22.6 points)
- v12: mean=0.220, 43% non-zero, 42 samples (partial eval — seq=8192 no regression)
- Leaderboard top: vera6 50.56, affshoot 49.44, wisercat 47.14 (Block 7776423)
- Parse error: ~0% (v9+)
- Best games: leduc_poker (full win), goofspiel (100%)
- Worst: othello, hex, liars_dice, clobber (0% — SFT-unlearnable)

## Improvement Directions
- **P0: More data for "unlearnable" games** — bots win at 55-79%, old data was bad quality not unlearnable. Even 10% eval → GAME 37→43.
- **P1: Increase leduc_poker + gin_rummy volume** — v4 batch2 adds 778 entries
- **P2: DPO on game outcomes** — 589 GAME pairs available, would help all games
- **P3: GRPO/RL for strategic games** — verifiable reward (win/lose) makes GAME ideal for RL

### Score Ceiling Analysis
| Scenario | Learnable | Unlearnable | GAME Score |
|----------|-----------|-------------|------------|
| Current v2.1 | ~60% avg | 0% | 25.7 |
| Max learnable only | ~87% avg | 0% | 37.1 |
| +10% unlearnable | ~87% avg | 10% | 42.9 |
| Match #6 | ~87% avg | 20% | 48.6 |
| #1 target | ~92% avg | 30% | 56.4 |
