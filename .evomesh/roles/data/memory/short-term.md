# Short-term Memory

## Last active: 2026-03-27

### v20 Data on HF — 9999 entries, FINAL
- Fixed format: env=LIVEWEB, content!=""(not None), last_msg=assistant
- 4 domains: stooq 48% of gotos, coingecko 31%, hn 11%, taostats 10%
- Only goto+stop used in tool_calls (all 10 eval tools defined in schema)
- 93.5% entries visit 2+ sites, avg 6.4 gotos/entry
- HF synced 2026-03-27

### v2.25 ckpt-400 Eval Analysis
- 55 samples, mean 0.187, 32/55 zeros
- 18/55 infrastructure errors (CAPTCHA/timeout) — 18% waste
- Top failure: "data not collected" (model visits wrong URLs) — 65% of subtask failures
- HN weakest site (0.091 mean)
- Sent analysis to Strategist (inbox)

### Cache
- m1+m2: stooq symbol lowercased, 115 CAPTCHA entries identified
- GT case-mismatch: verified +22 points (14→36.8)

### HARD RULE: LIVEWEB ONLY
### NEVER push to liveweb-arena repo
