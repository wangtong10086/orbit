# Data Agent (LIVEWEB) — Active Tasks

## Completed
- [x] v13 single-turn + tools: 12054 entries (Qwen3 template think-drop fix + tools field alignment)
- [x] Root cause analysis: think blocks dropped in multi-turn, tools missing from training
- [x] Cache v2: 61 stooq + 23 coingecko + taostats + HN on m1+m2 (all 70 eval task_ids covered)
- [x] NW verified NOT affected by think-drop (uses role:tool, not role:user between steps)
- [x] Notified strategist + trainer of all fixes
- [x] Cache v4: ALL placeholder entries replaced with real HTML+accessibility_tree+api_data on m1+m2 (4528 real / 4708 total pages)

## Active
- [ ] Design data fix for premature stopping (41% null GT issue) — awaiting strategist directive

## Completed
- [x] v2.23 eval analysis: null GT is #1 issue (41% answers), cache fix validated (errors 30%→7%)
- [x] Sent findings to strategist with improvement proposals

## Backlog
- [ ] Cache expansion: ^ftse, ^n225, usdgbp, gbpeur etc.
- [ ] OpenLibrary cache: 12 eval tasks use OL but site returns 429 — no fix yet
- [ ] Test with --reasoning-parser qwen3 (may fix tool call corruption)
