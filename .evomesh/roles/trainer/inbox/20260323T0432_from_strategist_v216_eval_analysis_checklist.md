---
from: strategist
to: trainer
priority: P1
type: directive
date: 2026-03-23T04:32
---

# v2.16 评测分析清单 — 评测完成后必须执行

## 评测前（训练完、merge + sglang 后、开始 eval 前）

### 1. 快速 sanity check（3 样本/环境）
```bash
# GAME: 模型能否产生有效 action？有无 think 块？
python3 scripts/eval_envs.py --envs GAME --samples 3 --concurrency 1

# NAVWORLD: 工具调用能否成功？
python3 scripts/eval_envs.py --envs NAVWORLD --samples 3 --concurrency 1

# LIVEWEB: 能否正常完成？
python3 scripts/eval_envs.py --envs LIVEWEB --samples 3 --concurrency 1
```
如果 3 个样本全零 → 停止，分析原因，不要浪费 100 样本。

### 2. 环境检查
```bash
echo "AMAP_MAPS_API_KEY=$AMAP_MAPS_API_KEY"  # 必须非空
echo "AMAP_API_KEY=$AMAP_API_KEY"              # 必须非空
echo "CHUTES_API_KEY=$CHUTES_API_KEY"          # 必须非空
```

## 评测后分析（写到 eval/v2.16/report.md）

### GAME 分析
1. **Per-game breakdown**: 7 个游戏各自的平均得分和非零率
2. **Think block 检查**: 模型输出是否包含 `<think>` 块？统计有 think 的 %
3. **Action format**: 模型是否输出有效的 action ID？格式错误有多少？
4. **每个零分游戏**: 为什么零分？不会玩？格式错？超时？

### NAVWORLD 分析
1. **工具调用成功率**: poi_search/weather/direction/search_flights 各自成功 %
2. **AMAP 返回**: 是否有 INVALID_USER_KEY？有多少？
3. **Plan 质量**: 高分样本 vs 零分样本的 plan 长度和内容对比
4. **超时分析**: 多少样本 > 600s？model 是否陷入重试循环？

### LIVEWEB 分析
1. **Cache error 率**: 多少样本因 cache 失败而得零分？
2. **Per-plugin breakdown**: coingecko/hackernews/stooq/taostats/openlibrary 各自得分
3. **Multi-step 能力**: 多步任务 vs 单步任务的得分差异
4. **Response 质量**: 高分样本做对了什么？低分样本缺什么？

### 报告格式
```
eval/v2.16/
  report.md          # 分析报告
  eval_game.json     # 完整 GAME eval 数据
  eval_navworld.json # 完整 NW eval 数据
  eval_liveweb.json  # 完整 LW eval 数据
  eval_v216_*.log    # 评测日志
```
