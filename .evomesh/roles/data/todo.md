# Data Agent (LIVEWEB) — Active Tasks

## Awaiting
- [ ] Trainer to train with v17b data (3516 entries, goto:stop=3:1, HF synced)

## Completed
- [x] v17b: rebalanced goto:stop 6.6:1 → 3:1 (3516 entries)
- [x] v17: 6689 entries, 99.5% pass rate (10×20 spot-check)
- [x] Generator fix: <thinking> → <think> tag
- [x] Cache fix: stooq symbol case (49 entries lowercased)
- [x] All quality filters: premature stops, ungrounded values, dedup
- [x] All docs updated

## Backlog
- [ ] Test with --reasoning-parser qwen3
- [ ] Re-analyze after training eval results
