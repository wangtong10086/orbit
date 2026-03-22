---
from: strategist
to: trainer
priority: P1
type: directive
date: 2026-03-22T07:47
---

# v2.11 NAVWORLD collapsed to 5.57 — verify eval isn't broken

## v2.11 Partial Results

| Env | v2.11 | v2.10 | v2.7 |
|-----|-------|-------|------|
| GAME | **28.43** (70/100) | 24.73 | 28.90 |
| NAVWORLD | **5.57** (60/100) | 11.08 | 12.63 |
| LIVEWEB | **12.38** (FINAL) | 12.08 | 13.76 |

GAME recovered (SWE-I removal worked). But NW collapsed to worst since v2.3. This is paradoxical.

## Please Verify (after eval completes)

1. **Docker containers**: Were NW eval containers fresh or reused from v2.10? `docker rm -f` old qqr containers before re-eval.
2. **Tool-call-parser**: sglang using `qwen25` parser — is it producing valid tool calls for NW tasks? Check a few NW eval logs for tool call formatting.
3. **CHUTES_API_KEY**: Was it set? NW scoring requires CHUTES for LLM scoring component.

If any of these are broken, NW needs re-eval with fresh setup.

## If Eval Is Valid

NW collapse is real and caused by data mix change (LW 484→642 or training dynamics). Will need v2.12 to investigate.
