# Short-term Memory

## Last active: 2026-03-25

### GT Case-Mismatch Fix VERIFIED: 14→36.8 (+22 points!)
- Fix: `gt_collector.py` normalize stooq symbol to lowercase
- 6/20 samples: mean=36.8, null GT 27% (was 41%), accuracy 53% (was 24%)
- Commit `503b08a` in repos/liveweb-arena (NOT pushed, per user instruction)
- Also includes block_patterns.py stealth fix and hybrid/utils.py case fix

### Teacher Bot Improvement Proposal Written
- `knowledge/liveweb_teacher_improvements.md` — 5 specific code changes
- Focus: precise tree evidence, computation steps, data completeness check
- Expected: additional +10-15 points on top of GT fix → 46-52 total

### Eval on m1: v223_gtfix2, 20 samples, concurrency=1, running
- sglang with v2.23 ckpt-550 model
- Volume mounts: gt_collector_fixed.py + hybrid_utils_fixed.py + block_patterns_fixed.py

### HARD RULE: LIVEWEB ONLY
