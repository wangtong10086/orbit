# Short-term Memory

## Last active: 2026-03-25

### v15 Data Generated and Uploaded
- 39114 single-turn entries from 5465 composite trajectories
- Balanced: 2-sub 33%, 3-sub 33%, 4-sub 33%
- 0% vague think blocks, 67% with explicit tree evidence
- Sites: coingecko 33%, stooq 28%, taostats 27%, HN 8%
- HF synced (548MB)

### Fixes Applied
- Stooq cache symbol case: 49 entries lowercased on m1+m2
- Teacher generator plugin URL normalization (official commit 2c02500)
- Teacher think quality: tree evidence, computation steps (commits 60c12c9, c385bd3)
- Taostats rendering: partial fix (35/128 subnets, needs ALL button fix)

### Remaining Official Code Changes Needed
1. Taostats ALL button: only 35/128 subnets visible in tree (need verification + longer wait)
2. Stooq api_client: symbol should return lowercase to prevent cache rebuild issues

### HARD RULE: LIVEWEB ONLY
### NEVER push to liveweb-arena repo (origin=official, unango=fork)
