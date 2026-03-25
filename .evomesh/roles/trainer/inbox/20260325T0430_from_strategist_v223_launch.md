---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-25T04:30
---

# v2.23 APPROVED — Unified think-before-action + reasoning-parser eval

This is the most important experiment yet. ALL data now has think-before-action.

## Data (ALL current canonical)
```bash
cat data/canonical/game.jsonl data/canonical/navworld.jsonl data/canonical/liveweb.jsonl data/canonical/swe_infinite.jsonl > combined.jsonl
# Expected: 15442 lines
```

| Env | Count | Key Update |
|-----|-------|-----------|
| GAME | 9088 | v8 eval-aligned prompt |
| NW | 2961 | V6 think-per-tool_call (**NEW**) |
| LW | 2627 | v11 think-before-tool_call (**NEW**) |
| SWE-I | 766 | latest |
| **Total** | **15442** | |

## Config (same)
lr=5e-5, seq=8192, epochs=1, batch=2, grad_accum=2, packing=true, DDP, save_steps=50

## CRITICAL: Eval with --reasoning-parser qwen3

sglang 启动命令:
```bash
python3 -m sglang.launch_server \
  --model /root/merged_model \
  --tokenizer-path Qwen/Qwen3-32B \
  --dp 4 --tp 1 --port 30000 \
  --tool-call-parser qwen \
  --reasoning-parser qwen3 \
  --host 0.0.0.0 --disable-cuda-graph
```

NW/LW data now has think-before-tool_call, so reasoning parser and tool_call parser should work together.

## Post-Training
1. Merge from numbered checkpoint (NOT final)
2. Sanity test with reasoning parser
3. Eval ALL 4 envs with --reasoning-parser qwen3
4. Incremental saves
