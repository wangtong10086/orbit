# Short-term Memory

## Last active: 2026-03-26

### v19b Data on HF — 8816 entries, FINAL
- 0% ungrounded (184 removed), 100% <think>...</think>, tools=BROWSER_ACTIONS
- Site: tao 27%, cg 27%, stooq 22%, hn 5%, planning 16%
- Entities: 53 stooq symbols, 39 CG coins, 127 taostats subnets
- Tasks: ranking 60%, percentage 37%, group 15%, portfolio 8%, summary 8%
- Subtasks: 1s 20%, 2s 26%, 3s 26%, 4s 26%
- goto:stop = 4.6:1

### Generator Fixes (training branch)
- commit a98e4f2: <think> tag, compact tree, composite timeout, stooq init timeout
- commit de9429d (official): DRY compact tree, prompt/doc tag fix
- LIVEWEB_CACHE_TTL=999999999 required when generating

### Cache
- m1+m2: stooq symbol lowercased, 115 CAPTCHA entries identified (awaiting official cache fix)
- GT case-mismatch: verified +22 points (14→36.8)

### HARD RULE: LIVEWEB ONLY
### NEVER push to liveweb-arena repo
