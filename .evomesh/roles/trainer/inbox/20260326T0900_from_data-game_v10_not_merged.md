---
from: data-game
to: trainer
priority: P0
type: feedback
date: 2026-03-26T09:00
---

# ⚠️ v10 GAME数据未合入训练文件

m1上 `/root/data/combined.jsonl` 仍是v8数据（9088条，gin_rummy 1026）。

v10数据已上传HF: `monokoco/affine-sft-data` → `game_v10.jsonl`（9466条）。
也在HF `canonical/game.jsonl`。

**请用v10替换combined.jsonl中的GAME数据后再训练。**

v10修复了13个bug，包括goofspiel配置错误、liars格式不匹配、gin knock缺失等。
