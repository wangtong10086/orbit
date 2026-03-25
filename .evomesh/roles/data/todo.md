# Data Agent (LIVEWEB) — Active Tasks

## Completed
- [x] v13 single-turn + tools: 12054 entries (Qwen3 template think-drop fix + tools field alignment)
- [x] Root cause analysis: think blocks dropped in multi-turn, tools missing from training
- [x] Cache v2: 61 stooq + 23 coingecko + taostats + HN on m1+m2 (all 70 eval task_ids covered)
- [x] NW verified NOT affected by think-drop (uses role:tool, not role:user between steps)
- [x] Notified strategist + trainer of all fixes
- [x] Cache v4: ALL placeholder entries replaced with real HTML+accessibility_tree+api_data on m1+m2 (4528 real / 4708 total pages)

## Awaiting Official Changes
- [ ] Taostats table rendering fix (setup_page_for_cache wait for rows) → knowledge/liveweb_fundamental_fixes.md
- [ ] Teacher bot improvements (training branch has partial fixes) → knowledge/liveweb_teacher_improvements.md
- [ ] After fixes: regenerate training data + repopulate taostats cache

## Completed
- [x] Stooq cache symbol case fix: 49 entries lowercase on m1+m2 (score 14→36.8 verified)
- [x] ROOT CAUSE: taostats tree empty (97.6% "No Rows To Show") → 9% accuracy
- [x] All root cause analysis documented in knowledge/liveweb_fundamental_fixes.md
- [x] GT case-mismatch analysis + teacher bot proposal
- [x] Cache v4: real HTML+tree+api_data on m1+m2
- [x] v13 single-turn data (12054 entries)

## Backlog
- [ ] Test with --reasoning-parser qwen3
- [ ] Cache expansion: taostats subnets, missing stooq/forex symbols
