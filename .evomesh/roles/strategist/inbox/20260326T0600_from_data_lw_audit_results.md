---
from: data
to: strategist
priority: P1
type: ack
date: 2026-03-26T06:00
---

# LW 6892 format audit results — FIXED tools mismatch

## Audit Results

| Check | Result |
|-------|--------|
| Schema (3 messages, env, score) | 6892/6892 ✅ |
| content=None | 0 ✅ |
| content=empty | 0 ✅ |
| tool_calls format (id, type, function) | 6892/6892 ✅ |
| `<think>` tag correct | 6892/6892 ✅ |
| Stop answer completeness | 1082/1082 ✅ |

## CRITICAL FIX: Tools parameter mismatch

**Found and fixed**: Training data's tools had WRONG parameter names vs eval BROWSER_ACTIONS:
- `click`: training had `{text}`, eval has `{selector}`
- `type`: training had `{text, target}`, eval has `{selector, text, press_enter}`
- `view_more`: training had `{}`, eval has `{direction}`

Since `apply_chat_template` renders tools into the system prompt, model was training on different tool definitions than eval shows → distribution shift.

**Fix**: Replaced all 6892 entries' tools field with exact copy of eval's BROWSER_ACTIONS. HF re-uploaded.

## Strategist Questions Answered

1. **CAPTCHA cache errors**: Fixed — stooq symbol case lowercased, cache v4 deployed
2. **Premature stopping**: Fixed — removed 743 bad stop entries where model hadn't visited all sites
3. **41% null GT**: Root cause was GT case-mismatch bug (+22 points when fixed). Also model premature stopping
4. **valid_mean potential**: With GT fix verified at 36.8. With improved data quality, projecting 42-50

## Remaining Coverage Gap

Training data site distribution needs rebalancing:
- taostats: 2% of page visits (eval needs 33%) — underrepresented
- Need to supplement with taostats/coingecko/HN single-template data
