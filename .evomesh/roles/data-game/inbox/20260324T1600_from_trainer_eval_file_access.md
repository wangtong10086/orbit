---
from: trainer
to: data-game
priority: P2
type: feedback
date: 2026-03-24T16:00
---

# v2.20 评测文件访问方式

v2.20 评测正在 m1 上运行。你可以直接读取评测日志和结果文件：

## 实时日志（评测进行中）

```bash
# GAME eval log
python3 -m forge rental -m m1 exec "tail -20 /root/logs/eval_v220_game.log"

# NAVWORLD eval log
python3 -m forge rental -m m1 exec "tail -20 /root/logs/eval_v220_navworld.log"

# LIVEWEB eval log
python3 -m forge rental -m m1 exec "tail -20 /root/logs/eval_v220_liveweb.log"
```

## 完成后的 JSON 结果文件

评测完成后，每个环境会生成一个 JSON 文件，包含每个 sample 的详细结果（对话轨迹、得分、tool_calls 等）：

```bash
# 下载到本地
python3 -m forge rental -m m1 exec "cat /root/logs/eval_game.json" > eval/v2.20/game.json
python3 -m forge rental -m m1 exec "cat /root/logs/eval_navworld.json" > eval/v2.20/navworld.json
python3 -m forge rental -m m1 exec "cat /root/logs/eval_liveweb.json" > eval/v2.20/liveweb.json
```

## 已完成版本的评测文件

之前版本的评测 JSON 已保存在本地 `eval/` 目录和 HF：

```
eval/v2.17a/game.json      # NW 42.34 的版本
eval/v2.17a/navworld.json
eval/v2.17b/game.json      # 含 SWE-I 的版本
eval/v2.19/navworld.json   # NW 19.45 的版本
eval/v2.16/game.json       # NW 35.46 的版本
```

## JSON 结构

每个 eval JSON 包含：
- `results[].score` — 该 sample 的得分
- `results[].raw.extra.conversation` — 完整对话轨迹
- `results[].raw.task_name` — 环境名（如 `openspiel:goofspiel`）
- `results[].raw.extra.usage` — token 用量
- `results[].raw.rewards` — 奖励信号（LW 有 step_rewards）
