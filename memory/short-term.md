# Short-Term Memory — Session 2026-03-18

## Context
- Inherited project from /home/dev/work/train/affine-forge (old repo, 12 iterations v1-v12)
- New repo: /home/claudeuser/work/affine-swarm (fresh v1 start)
- Old machine decommissioned, awaiting new machine from user

## Key Correction
- GAME scheduling weight 3.0 = sampled 3x more by validators, NOT 3x scoring weight
- Scoring uses smoothed geometric mean (epsilon=0.1) across all environments equally
- DECAY_FACTOR=0.5: rank 2 gets 50% of rank 1's weight — ranking matters a lot
- MAX_LAYERS=6: higher layers (more envs combined) have exponentially more weight

## Scoring Mechanism Deep Dive (from affine-cortex source code)
- Stage 3 generates all environment subsets (L1=single, L2=pairs, L3=triples...)
- Layer weights: N * 2^(layer-1) — L6 is 32x more important than L1
- Within each subset: geometric mean of env scores, then rank miners, apply 0.5 decay per rank
- GEOMETRIC_MEAN_EPSILON=0.1: zero scores are smoothed, not instantly fatal
  - A zero becomes (0+0.1)=0.1, not 0. Still bad but not catastrophic.
  - Implication: "barely scoring" vs "zero" is a meaningful distinction
- GAME has ENV_THRESHOLD_CONFIG z_score=1 (easier to beat in anti-copy filter)
- PRINT/SWE-SYNTH have z_score=2.0 (harder to beat)

## Role Design Decision
- Conclusion: optimize existing 2 roles, don't add a 3rd
- Executor stays as-is (on-demand, not a constant loop role)
- Core changes:
  1. Trainer: core duty becomes experiment design + hypothesis verification
  2. Data Agent: gains data mix veto power, must propose mix based on gap analysis
  3. Adversarial review: forced trigger before every training launch
  4. Shared quantitative framework: gap_analysis in experiments/

## Completed This Session
1. Copied canonical data (12,194 entries, 7 envs) to data/canonical/
2. Updated knowledge files with v11-v12 learnings
3. Reset experiments/results.tsv for fresh v1
4. Rewrote PLAYBOOK.md with new strategy
5. Updated prompts with operational wisdom
6. Created full audit report: knowledge/audit_report.md
7. Fixed GAME 3x weight misunderstanding across all docs
8. Read affine-cortex scorer source code — understood full scoring algorithm

## Next Steps
- Rewrite .evomesh role definitions (trainer, data)
- Rewrite prompts/loop_main.md and prompts/data_synth.md
- Update knowledge with scoring mechanism details
- Await new machine from user
