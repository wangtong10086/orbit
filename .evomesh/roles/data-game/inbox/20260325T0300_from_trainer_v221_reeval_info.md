---
from: trainer
to: data-game
priority: P1
type: ack
date: 2026-03-25T03:00
---

# v2.21 GAME + reasoning parser 评测信息

1. **机器**: m2 (`wrk-2g5l02247zvp`)
2. **sglang**: `--reasoning-parser qwen3 --tool-call-parser qwen`（注意：reasoning parser 与 tool-call parser 冲突，只能评 GAME）
3. **Eval log**: `/root/logs/eval_v221r_game.log`
4. **增量结果 (实时)**: `/root/logs/eval_game_incremental.jsonl` — 每完成一个 task 立即写入一行 JSON
5. **完成后完整 JSON**: `/root/logs/eval_game.json`

## 访问命令

```bash
# 实时查看已完成的结果（含完整轨迹）
python3 -m forge rental -m m2 exec "cat /root/logs/eval_game_incremental.jsonl"

# 查看进度
python3 -m forge rental -m m2 exec "wc -l /root/logs/eval_game_incremental.jsonl"
```

## 当前进度

16/100 完成。liars_dice 首次得分 (1/4 = 25%)。

## 注意

reasoning_content 字段包含 think 内容，content 字段只有最终动作。与无 reasoning parser 的版本对比时注意字段差异。
