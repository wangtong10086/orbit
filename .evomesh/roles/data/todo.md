# Data Agent (LIVEWEB) — Active Tasks

## Awaiting
- [ ] Trainer to train with v19b data (8816 entries, HF synced)

## Completed
- [x] v19b: 8816 entries, 0% ungrounded, 100% <think> tag, tools=BROWSER_ACTIONS
- [x] Generator fixes committed (a98e4f2 + de9429d on training branch)
- [x] Cache fixes: stooq symbol case, 115 CAPTCHA entries identified
- [x] 150-entry audit: 94% strict pass → 184 false-positive removed → 0% true ungrounded
- [x] Coverage: tao 27%/cg 27%/stooq 22%/hn 5%, 53 symbols, 39 coins, 127 subnets
- [x] All docs updated: synth_config, LIVEWEB.md, todo

## Backlog
- [ ] Test with --reasoning-parser qwen3
- [ ] Re-analyze after v19b training eval results
- [ ] Cache cleanup: remove 115 CAPTCHA entries on m1+m2 (after official cache fix)
