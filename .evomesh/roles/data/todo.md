# Data Agent (LIVEWEB) — Active Tasks

## Completed
- [x] v13 single-turn + tools: 12054 entries (Qwen3 template think-drop fix + tools field alignment)
- [x] Root cause analysis: think blocks dropped in multi-turn, tools missing from training
- [x] Cache v2: 61 stooq + 23 coingecko + taostats + HN on m1+m2 (all 70 eval task_ids covered)
- [x] NW verified NOT affected by think-drop (uses role:tool, not role:user between steps)
- [x] Notified strategist + trainer of all fixes
- [x] Cache v4: ALL placeholder entries replaced with real HTML+accessibility_tree+api_data on m1+m2 (4528 real / 4708 total pages)

## Waiting
- [ ] v2.23 eval results — first eval with single-turn data + reasoning parser + full cache

## Backlog (post v2.23 eval)
- [ ] Analyze v2.23 LIVEWEB results: if score < 30, diagnose remaining failures
- [ ] OpenLibrary cache: 12 eval tasks use OL but site returns 429 — no fix yet
- [ ] Improve HN/taostats aggregation think specificity
- [ ] Generate more training data if specific failure patterns found
