# Data Agent (LIVEWEB) — Active Tasks

## Awaiting
- [ ] Trainer to train with v17 data (7049 entries, HF synced)

## Completed
- [x] v17 final data: 7049 entries, all quality checks passed (10/10 spot-check ✅)
- [x] Removed 751 bad stop entries (premature stopping before visiting all sites)
- [x] Fixed <thinking> → <think> tag (Qwen3 compatibility)
- [x] 100% Recent Actions context, 100% stop answer completeness
- [x] GT case-mismatch analysis + cache fix on m1+m2
- [x] All root cause analysis documented

## Backlog
- [ ] Test with --reasoning-parser qwen3
- [ ] Re-analyze after v17 training eval results
