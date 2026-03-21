# GAME Environment

## Key Facts
- 7 active games, eval uses OpenSpiel + MCTS opponent (except goofspiel: simultaneous → random)
- `strip_think_tags=True` — think blocks fully removed before action parsing
- Scoring: geometric mean across environments, scheduling weight 3.0
- Config variants per game: board sizes, card counts, etc. (from `generate_game_params`)

## Active Games + Bot Win Rate (GPU verified, vs MCTS, 2026-03-21)

| idx | Game | MCTS Config | Bot Win Rate | v2.7 Eval | Bot Strategy |
|-----|------|------------|-------------|-----------|-------------|
| 0 | **goofspiel** | random (simultaneous) | **90%** (9/10) | 91.7% | 比例出价 + 终局调整 |
| 1 | **liars_dice** | 3000sim,200roll | **~10%** | 10.0% | 混合策略+概率, MCTS太强 |
| 2 | **leduc_poker** | 3000sim,200roll | **~60%** | 45.9% | 决策表 + fold J on non-J |
| 3 | **gin_rummy** | 500sim,10roll | **~50%** | 47.6% | near-meld + knock≤5 + hand parse fix |
| 4 | **othello** | 1000sim,20roll | **~67%** | 0% | minimax depth 4-10 + 位置权重 + board parse |
| 6 | **hex** | 1000sim,50roll | **~33%** | 0% | minimax + BFS + 虚连接 (v6 testing) |
| 7 | **clobber** | 1500sim,100roll | **~5%** | 0% | minimax + move ordering + parity (v6 testing) |

## Zero-Score Root Cause (CONFIRMED)

v2.7 eval 日志确认：零分游戏模型输出纯数字（解析成功），但策略太差输给 MCTS。
训练数据 vs random 对手不匹配 eval 的 MCTS 对手。
解决方案：使用 `game_bot_gen_mcts.py` 生成 vs MCTS 数据。

## Canonical: 5888 entries
- 保留所有已产出得分的数据（v2.7 基线）
- 新 vs MCTS 数据生成后增量合并

## Bot 迭代优化

**方法**: GPU 10局测试 → 分析对局细节（wins + losses） → 改进 bot → 循环
**不做 think rewrite** — 直接在 bot 中生成推理式 think

各游戏独立启动测试（耗时差异大）：
- 快: leduc/goofspiel (~1min/10局), liars_dice (~2min)
- 慢: gin_rummy (~10min), hex (~10min), othello/clobber (~15min)

## 工具链

| 文件 | 用途 |
|------|------|
| `scripts/game/game_bot_gen_mcts.py` | 数据生成 — bot vs MCTS (MCTS baked in) |
| `scripts/game/{game}_bot.py` | 各游戏优化策略 |
| `scripts/game_bots.py` | 7 游戏 bot 策略主文件 |
| `scripts/game_distill.py` | GPT-5.4 蒸馏 |

```bash
# GPU 测试命令：
PYTHONPATH=/root/game_gen:/root/game_gen/game OPENSPIEL_DIR=/root/affinetes/environments/openspiel \
  python3 /root/game_gen/game/game_bot_gen_mcts.py --game {GAME} -n 10 \
  -o /root/game_gen/mcts10_{GAME}.jsonl
```
