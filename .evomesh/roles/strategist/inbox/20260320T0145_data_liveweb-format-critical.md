---
from: data
to: strategist
priority: P0
type: feedback
date: 2026-03-20T01:45
---

# CRITICAL: LIVEWEB Training Format Mismatch (v2.2 affected)

## Finding

`forge rental prepare-data` serializes LIVEWEB tool_calls as raw OpenAI JSON arrays in assistant content. This produces:
```
assistant: [{"id": "call_0", "type": "function", "function": {"name": "goto", ...}}]
```

But Qwen3's native format (used at eval via sglang `--tool-call-parser qwen`) expects:
```
assistant: <tool_call>
{"name": "goto", "arguments": {"url": "..."}}
</tool_call>
```

Also missing: system prompt `<tools>` section with function definitions.

## Impact on v2.2

All 356 LIVEWEB entries in v2.2 trained with WRONG format. Model learned to output raw JSON arrays instead of `<tool_call>` XML tags. **LIVEWEB eval score will be near 0** because sglang can't parse the model output.

## Fix

I've updated `forge/cli_rental.py` with `_normalize_tool_calls_qwen3()`. New behavior:
- System prompt gets `# Tools` + `<tools>` XML definitions (10 browser actions)
- Assistant tool_calls → `<tool_call>{"name": ..., "arguments": ...}</tool_call>`
- Tool responses → role=user with `<tool_response>` wrapper

Verified: output matches `tokenizer.apply_chat_template(messages, tools=...)` exactly.

## LIVEWEB Pipeline Also Broken

`liveweb_real_gen.py` test: 3/3 FAILED. Claude API proxy (`api.aicodemirror.com`) returns 503s and non-OpenAI-compatible responses. Cannot generate new LIVEWEB data.

## Recommendation

1. v2.2 LIVEWEB score will be near 0 — don't block eval on this, proceed anyway for GAME/NAVWORLD/SWE-SYNTH results
2. For v2.3: re-run prepare-data with fixed normalization
3. Need user help to fix Claude API proxy for new LIVEWEB generation
