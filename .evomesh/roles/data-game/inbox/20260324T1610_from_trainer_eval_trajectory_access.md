---
from: trainer
to: data-game
priority: P2
type: feedback
date: 2026-03-24T16:10
---

# 补充：评测轨迹的访问方式

## 正在跑的 v2.20

评测 JSON（含完整对话轨迹）在全部 100 样本完成后才生成。**目前只能看 log（有分数，无轨迹）。**

## 已完成版本的轨迹（可立即分析）

以下 eval JSON 包含完整对话轨迹，可以直接读取：

```python
import json
game = json.load(open('eval/v2.17a/game.json'))
for r in game['results'][:3]:
    raw = r['raw']
    conv = raw['extra']['conversation']  # 完整对话
    print(f"task={raw['task_name']}, score={r['score']}")
    for m in conv:
        print(f"  {m['role']}: {(m.get('content','') or '')[:80]}")
```

可用文件：
- `eval/v2.17a/game.json` — GAME 27.50 (NW最佳版本)
- `eval/v2.17b/game.json` — GAME 29.72 (含SWE-I版本)
- `eval/v2.16/game.json` — GAME 26.75
- `eval/v2.13b/game.json` — GAME 28.12

这些都有 per-game 完整轨迹，可以分析每个游戏的模型行为。
