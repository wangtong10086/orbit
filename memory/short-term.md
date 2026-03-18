# Short-Term Memory — Session 2026-03-18

## Context
- Inherited project from /home/dev/work/train/affine-forge (old repo, 12 iterations v1-v12)
- New repo: /home/claudeuser/work/affine-swarm (fresh v1 start)
- Old machine decommissioned, awaiting new machine from user

## Completed This Session
1. Copied canonical data (12,194 entries, 7 envs) to data/canonical/
2. Inherited iteration_log.md (removed — Chinese content violates CLAUDE.md rules, learnings in knowledge/*.md)
3. Updated knowledge files with v11-v12 learnings
4. Updated synth_config.json with current data state
5. Reset experiments/results.tsv for fresh v1
6. Rewrote PLAYBOOK.md with new strategy
7. Updated prompts (loop_main.md, data_synth.md) with operational wisdom
8. Committed inheritance changes
9. Created full audit report: knowledge/audit_report.md
10. Fixed GAME 3x weight misunderstanding across all docs

## Key Correction
- GAME scheduling weight 3.0 = sampled 3x more often by validators (more data points)
- This is NOT a 3x scoring weight — geometric mean treats all environments equally
- All past iterations over-prioritized GAME in data mix based on this misunderstanding

## Audit Findings (12 iterations review)
Full report: knowledge/audit_report.md

9 systemic issues:
1. Scoring mechanism misunderstood (GAME treated as 3x priority, it's not)
2. Multiple variables changed per iteration — no controlled experiments
3. Eval sample sizes too small (20) in early versions — false signals
4. No regression testing across all environments
5. Data mix imbalanced (LGC-v2+PRINT=51% of data for potentially deprecated envs)
6. NAVWORLD SFT plateau (3.4x data -> only 12% improvement)
7. GAME structural ceiling (othello/hex/liars_dice always 0%)
8. DPO pipeline built but never used (6 days sitting idle)
9. No systematic leaderboard gap analysis framework

## Next Steps
- User to provide new machine
- Plan v1 training with all corrections applied
- DPO experiment priority elevated (SFT clearly plateauing)
- Data mix rebalance based on geometric mean optimization
