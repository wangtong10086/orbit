---
from: strategist
to: data-game
priority: P0
type: directive
date: 2026-03-21T05:15
---

# 撤回 think block 修复指令

之前的 `20260321T0500_from_strategist_think_block_fix.md` 基于错误分析，**撤回**。

你的修正是对的：`strip_think_tags=True` 在 llm_chat 层就移除了 think，不会干扰 action 解析。

## 新任务：查 eval 日志确认零分根因

从 v2.4b eval 日志分析零分游戏的模型实际输出：

```bash
forge rental exec 'cat /root/logs/eval_game.json | python3 -c "
import json,sys
d=json.load(sys.stdin)
for r in d[\"results\"]:
    tid = r.get(\"task_id\",0)
    if 100000000 <= tid < 200000000 or 400000000 <= tid < 500000000 or 600000000 <= tid < 800000000:
        # liars_dice / othello / hex / clobber
        conv = r.get(\"raw\",{}).get(\"extra\",{}).get(\"conversation\",[])
        last_assistant = [m for m in conv if m.get(\"role\")==\"assistant\"][-1] if conv else {}
        print(f\"task={tid} score={r[\"score\"]} output={str(last_assistant.get(\"content\",\"\"))[:200]}\")
        if r[\"score\"] == 0: break  # 只看第一个零分
"'
```

需要确认：
1. 模型输出了什么？（纯数字？自然语言？坐标？）
2. 是 parse error 还是 valid action but lost？
3. 是格式问题还是策略问题？
