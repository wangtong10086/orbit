# Short-term Memory

## Last active: 2026-03-30

### LIVEWEB Data: 30,000 entries on HF
- Composite 2/3/4 subtask only, single-step format
- 5 plugins: hybrid 22.7%, hackernews 22.2%, taostats 18.6%, coingecko 18.5%, stooq 18.1%
- 3,338 unique templates, max 64/template
- `forge data audit` ALL PASS

### Latest Eval: v2.28 ckpt1200 = 39.66
- Up from v2.25 best of 27.76 (+43%)
- Weakest: stooq 32.1, hackernews 33.9

### Eval image switched to self-build
- `scripts/eval_envs.py` changed: `liveweb-arena:eval` built from `repos/liveweb-arena`

### HARD RULE: LIVEWEB ONLY
### NEVER push to liveweb-arena repo
