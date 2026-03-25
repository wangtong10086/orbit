# Data Agent (LIVEWEB) — Active Tasks

## Completed
- [x] v13 single-turn + tools: 12054 entries (Qwen3 template think-drop fix + tools field alignment)
- [x] Root cause analysis: think blocks dropped in multi-turn, tools missing from training
- [x] Cache v2: 61 stooq + 23 coingecko + taostats + HN on m1+m2 (all 70 eval task_ids covered)
- [x] NW verified NOT affected by think-drop (uses role:tool, not role:user between steps)
- [x] Notified strategist + trainer of all fixes
- [x] Cache v4: ALL placeholder entries replaced with real HTML+accessibility_tree+api_data on m1+m2 (4528 real / 4708 total pages)

## Active
- [ ] Awaiting user to push GT fix to liveweb-arena official repo (commit 503b08a)
- [ ] Awaiting user to apply teacher bot improvements (knowledge/liveweb_teacher_improvements.md)
- [ ] GT fix eval running on m1: 6/20 done, mean=36.8 (+22 from baseline 14)

## Completed
- [x] GT case-mismatch bug found and fixed: score 14→36.8 (verified 6/20 samples)
- [x] Teacher bot improvement proposal written (5 specific changes)
- [x] v2.23 deep eval analysis: null GT + accuracy as root causes
- [x] Cache v4: all placeholder entries replaced with real data
- [x] Stealth Playwright fix (block_patterns.py)

## Backlog (after teacher bot improvements)
- [ ] Regenerate training data with improved teacher bot
- [ ] Test with --reasoning-parser qwen3
- [ ] Cache expansion: taostats subnets, missing stooq/forex symbols
