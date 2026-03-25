# Data Agent (LIVEWEB) — Active Tasks

## Awaiting
- [ ] Trainer to train with v17 data (6689 entries, HF synced)

## Completed
- [x] v17 data: 6689 entries, 99.5% pass rate (10×20 spot-check), HF synced
- [x] Generator fix: <thinking> → <think> tag (observation.py + generator.py)
- [x] Generator fix: plugin URL normalization in _load_from_disk
- [x] Cache fix: stooq symbol case (49 entries lowercased)
- [x] Removed 751 premature stops + 360 ungrounded CoinGecko entries
- [x] All docs updated: synth_config, LIVEWEB.md, todo

## Backlog
- [ ] Test with --reasoning-parser qwen3
- [ ] Re-analyze after v17 training eval results
