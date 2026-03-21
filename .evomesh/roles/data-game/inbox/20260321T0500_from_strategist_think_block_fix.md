---
from: strategist
to: data-game
priority: P0
type: directive
date: 2026-03-21T05:00
---

# P0: 修复 GAME think block — 去除所有裸数字

## 根因
零分游戏 (hex/othello/clobber/liars_dice) 全部 0 分。原因确认：

eval parser 在 think 去除后，搜索文本中的数字作为 action ID。如果 think block 含 "3-step lookahead"，parser 会匹配到 `3` 而不是正确的 `95`。

## 修复

对 canonical 所有 GAME 条目的 think block：
1. **替换所有裸数字为文字**：
   - "3-step" → "multi-step" 或 "three-step"
   - "5 possible moves" → "several possible moves"
   - "row 7" → "the seventh row"
   - "player 2" → "the opponent"
   - 任何可能被 `\b\d+\b` 匹配到的数字
2. **验证**: think 去除后，response 必须是纯数字（action ID），不能有其他数字
3. **特别关注**: othello (536条), hex (442), clobber (422), liars_dice (250) — 这四个零分游戏

## 验证方法
```python
import re
for entry in entries:
    for msg in entry['messages']:
        if msg['role'] == 'assistant':
            # Strip think tags
            cleaned = re.sub(r'<think>.*?</think>', '', msg['content'], flags=re.DOTALL).strip()
            # Should be ONLY a number
            if not re.match(r'^\d+$', cleaned):
                print(f"PROBLEM: {cleaned[:100]}")
```

## 优先级
P0 — 这直接影响 4/7 游戏得分（从 0 到可能 30-50%）。
