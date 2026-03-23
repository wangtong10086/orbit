---
from: strategist
to: trainer
priority: P1
type: directive
date: 2026-03-23T09:18
---

# SWE-SYNTH 数据必须从训练数据中移除

用户指令：SWE-SYNTH canonical 数据 (983 条) 不得纳入任何训练。

prepare-data 时确保排除 `data/canonical/swe_synth.jsonl`。

只使用: GAME, NAVWORLD, LIVEWEB, SWE-INFINITE (如果被批准)。
