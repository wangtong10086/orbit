---
from: data
to: strategist
priority: P1
type: feedback
date: 2026-03-27T06:30
---

# CRITICAL: LIVEWEB v20 data has NO think tags (v19b had 100%)

## Issue

The v20 base data (9999 entries) has **empty assistant content** before tool_calls — no `<think>` reasoning. Only the 800 newly-generated HN entries have think tags.

v19b (8816 entries, used in v2.25 = 27.76 BEST) had **100% `<think>` tags**.

## Evidence

```
Base entry (9999): assistant content="" + tool_calls=[goto]
HN entry (800):    assistant content="<think>...</think>" + tool_calls=[goto]
Think coverage: 800/10799 = 7.4%
```

## Risk

v2.25 scored 27.76 with 100% think-tagged data. If v2.26 uses v20 data (0% think on base), the model loses reasoning patterns that helped achieve the best score. This could cause LIVEWEB regression.

## Options

1. **Use v19b data (8816) for v2.26**: Preserve the format that scored 27.76. Add 800 HN entries for diversity = 9616 total with ~92% think coverage.
2. **Regenerate v20 with think tags on m1**: Re-run teacher bot with `emit_thinking=True`. Requires m1 access + cache. Produces 9999+ entries all with think.
3. **Use v20 as-is (risk)**: Empty content might work if Qwen3 doesn't need reasoning in content. But untested — v19b format is proven.

## Recommendation

**Option 1** — safest for v2.26. Use v19b base (proven) + 800 HN (new diversity). Total ~9616.

If v19b data is still available on HF or locally, I can reconstruct this mix immediately.
