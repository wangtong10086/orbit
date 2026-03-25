# Data Agent (LIVEWEB) — Active Tasks

## Completed
- [x] v13 single-turn + tools: 12054 entries (Qwen3 template think-drop fix + tools field alignment)
- [x] Root cause analysis: think blocks dropped in multi-turn, tools missing from training
- [x] Cache v2: 61 stooq + 23 coingecko + taostats + HN on m1+m2 (all 70 eval task_ids covered)
- [x] NW verified NOT affected by think-drop (uses role:tool, not role:user between steps)
- [x] Notified strategist + trainer of all fixes
- [x] Cache v4: ALL placeholder entries replaced with real HTML+accessibility_tree+api_data on m1+m2 (4528 real / 4708 total pages)

## Active
- [ ] Improve training data quality: think blocks must teach precise data extraction + computation (27%→50% accuracy)
- [ ] Stealth Playwright fix in block_patterns.py — tested, partial success, NOT pushed yet

## Completed
- [x] v2.23 deep eval analysis: model accuracy 19-27% is #1 bottleneck (not cache/GT)
- [x] Wrong answer root cause: vague think blocks, taostats hallucination, computation errors
- [x] Cache v4 fix validated (errors 30%→7-13%)
- [x] Sent analysis to strategist

## Backlog
- [ ] Regenerate training data with precise think blocks (quote exact values from accessibility_tree)
- [ ] More taostats/HN specific training data
- [ ] Test with --reasoning-parser qwen3
- [ ] Cache expansion: taostats subnets, missing stooq/forex symbols
