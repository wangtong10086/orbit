---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-23T03:20
---

# v2.15 评测必须全面分析 + v2.16 方向

## v2.15 评测完成后：必须做完整分析

按 ROLE.md 新规则，v2.15 评测完成后必须写 **每个环境的详细分析报告**：

### 每个环境必须回答：
1. **GAME**: per-game breakdown（7 个游戏各自得分多少？哪些游戏 0 分？）
2. **NAVWORLD**: 工具调用成功率（AMAP 是否正常？poi_search/weather/direction 成功率？）。对比 v2.13b 的 NW eval，找出得分差异的具体原因。
3. **LIVEWEB**: cache error 率。per-plugin breakdown（coingecko/hackernews/stooq/taostats 各自得分）。

### 报告格式
写到 `eval/v2.15/report.md`，rsync 所有 eval JSON 和 log 回本地。

## v2.16 方向（用户指令）

**用户明确要求**：
1. **v2.16 必须使用全部 GAME 数据**（当前 canonical 6511 条）——不再 subsample
2. **LW 分数低的问题必须单独解决**，不能靠牺牲其他环境的数据量来提升 LW
3. **各环境不应该被相互制衡**——每个环境的数据质量和训练方法应该独立优化

### LW 低分根因分析（需要做）

在写 v2.15 eval report 时，重点分析 LW 低分的根因：
- 是模型能力不足（不会处理某类任务）？
- 还是数据量不够（需要更多 LW 数据）？
- 还是数据质量问题（哪类 plugin 的数据质量差）？
- 还是 eval 基础设施问题（cache error, timeout）？

根据分析结果，LW 提升应该通过 **数据质量/数量改进** 解决，而不是调整比例。
