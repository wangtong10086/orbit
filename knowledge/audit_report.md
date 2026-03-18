# Training Audit Report — 12 Iterations Review

**Date**: 2026-03-18
**Scope**: v1-v12 from affine-forge (old repo), inherited to affine-swarm
**Total cost**: ~$150 ($80 infra debugging + $70 training)
**Effective training iterations**: 7 (v5-v12; v1-v4 was infra debugging)

---

## 1. Scoring Mechanism Misunderstanding

**Issue**: Throughout 12 iterations, GAME was treated as "3x weight, highest priority" in data mix decisions. This is wrong.

**Reality**:
- GAME scheduling weight 3.0 = sampled 3x more often by validators (more data points for evaluation)
- Scoring uses **geometric mean across ALL environments equally** — no per-env weight multiplier
- Subset scoring (L1 single, L2 pairs, L3 triples...) with exponentially growing layer weights
- Higher layers (more envs combined) matter exponentially more than single-env performance
- **Implication**: balance across ALL envs > excelling at one. Any zero kills all subsets containing that env.

**Impact on past decisions**:
- v1 was GAME-only training (4528 samples, 3 epochs) — suboptimal because it ignores 5 other envs
- GAME was consistently over-represented in data mix (34.7% in v10) while weaker envs were starved
- Strategic priority should have been: raise the floor of weakest envs, not max GAME

---

## 2. No Controlled Experiments

**Issue**: Every version changed 2-5 variables simultaneously.

| Version | Variables Changed |
|---------|------------------|
| v5→v6 | lr (1e-4→5e-5) + removed LGC-v2/PRINT + different data count |
| v6→v7 | lr (5e-5→1e-4) + unified system prompt + cleaned data |
| v7→v8 | added bot data (2193) + apply_chat_template + removed bad NAVWORLD |
| v8→v9 | added LGC-v2/PRINT back + NAVWORLD new key data + 90% more samples |
| v9→v10 | added MemoryGym + new rental |
| v10→v11 | NAVWORLD 3.4x increase (only clean change) |

**Impact**: When GAME went v5 0.16 → v6 0.09, was it lr? data removal? Both? Never root-caused. When NAVWORLD went v8 0.087 → v9 0.052, was it data quality or sample size?

**Rule going forward**: One variable per iteration. If multiple changes needed, split into separate experiments.

---

## 3. Evaluation Methodology Flaws

### 3a. Sample size too small
- v8 GAME/NAVWORLD: 20 samples each
- v8 NAVWORLD 0.087 (20 samples) → v9 0.052 (100 samples) — the "breakthrough" was variance
- 20 samples at 30% non-zero rate: standard error ≈ 0.10 — barely distinguishable from noise

### 3b. No cross-environment regression testing
- v6 removed LGC-v2/PRINT training data but never checked if GAME regressed
- SWE-SYNTH was never locally evaluated in any version (needs breaker service)
- LIVEWEB was never locally evaluated in any version (needs task set)
- When model improved on NAVWORLD, could have silently degraded on 3 other envs

### 3c. Eval config inconsistency
- v5-v8 used timeout=600s; v9+ used timeout=7200s
- GAME score jumped 0.10→0.19 purely from timeout change — not model improvement
- This makes v5-v8 GAME scores incomparable with v9+ scores

**Rules going forward**:
- Minimum 100 samples per environment per eval
- Eval ALL locally-testable envs every version (GAME + NAVWORLD minimum)
- Fix eval config (timeout=7200s, concurrency=4) and never change it

---

## 4. SFT Diminishing Returns

### NAVWORLD plateau
| Version | Data Count | Score | Change |
|---------|-----------|-------|--------|
| v8 | 605 | 0.087 (20s, unreliable) | — |
| v9 | 633 | 0.052 | true baseline |
| v10 | 633 | 0.051 | flat |
| v11 | 2154 (+240%) | 0.057 | +12% only |

Non-zero rate stuck at 23-28% across v9-v11. Model still fails 72% of tasks. More SFT data teaches format but not reasoning. Competitor RLStepone scores 33.7 using RL methods.

### GAME structural ceiling
| Tier | Games | SFT Score | Status |
|------|-------|-----------|--------|
| Solved | goofspiel | 100% | No improvement possible |
| Strong | leduc_poker, bridge, blackjack, euchre | 30-100% | Moderate gains possible |
| Bot-improved | gin_rummy, hearts | 0→100% with bots | Done |
| Always zero | othello, hex, liars_dice, clobber | 0% all versions | SFT cannot teach |
| Unlearnable | go, chess, checkers, solitaire | 0% all versions | Need search algorithms |

SFT ceiling ≈ 40-50 points. Top competitors score 45-65. Gap requires RL/search methods.

**Conclusion**: SFT alone cannot reach #1. DPO/RL is required for both NAVWORLD and GAME hard games.

---

## 5. DPO Pipeline — Built But Unused

- Built on 2026-03-12 (day 2 of project)
- 2688 preference pairs extracted (GAME 589, LGC-v2 800, NAVWORLD 241, PRINT 800, SWE-SYNTH 258)
- Config ready: beta=0.1, lr=5e-6, batch=1, grad_accum=8
- CLI command ready: `forge train dpo-launch`
- **Never tested in 6 days**

The iteration loop was stuck in "more data → SFT → eval → more data" cycle. No mechanism to break out and try fundamentally different approaches.

---

## 6. Data Mix Not Optimized for Geometric Mean

### Current mix (inherited)
| Env | Count | Share | Leaderboard Status |
|-----|-------|-------|-------------------|
| LGC-v2 | 3353 | 27.5% | May be removed |
| PRINT | 2898 | 23.8% | May be removed |
| NAVWORLD | 2248 | 18.4% | Active, weakest |
| GAME | 1415 | 11.6% | Active |
| SWE-SYNTH | 1351 | 11.1% | Active, never evaluated |
| MemoryGym | 499 | 4.1% | Not on leaderboard yet |
| LIVEWEB | 430 | 3.5% | Active, never evaluated |

**Issues**:
- 51.3% of data is LGC-v2+PRINT — potentially deprecated environments
- Weakest envs (NAVWORLD, LIVEWEB) are under-represented
- No evidence-based data mix optimization (just whatever DDB had + synthesis)
- Mix was never A/B tested (see point 2: no controlled experiments)

### Geometric mean implication
With geometric mean, the optimal strategy is to **equalize performance across environments**, not maximize any single one. If env A scores 50 and env B scores 5, improving B from 5→10 matters more than improving A from 50→60.

---

## 7. Infrastructure Tax

| Phase | Duration | Cost | Actual Training |
|-------|----------|------|-----------------|
| v1 (10 container attempts) | 2 days | ~$30 | ~0.5 runs |
| v2-v3 (HF upload bug) | 1 day | ~$40 | ~1 run |
| v4 (Targon outage) | 1 day | ~$30 | 0 runs |
| v5-v12 (actual training) | 4 days | ~$70 | 7 runs |

Infrastructure debugging consumed 47% of total spend. Now resolved:
- HF upload: subprocess isolation fix (verified)
- Targon network: offline wheel bundle (verified)
- Model download: pre-quantized unsloth/Qwen3-32B-bnb-4bit (verified)

With new machine (SSH, not Targon serverless), most infra issues should not recur.

---

## 8. Missing Analyses

### No leaderboard gap framework
Leaderboard snapshots were recorded but never systematically analyzed. Should compute per iteration:
```
priority_score[env] = (target_score - our_score) / target_score
```
Then sort by priority_score to determine data investment.

### No loss-to-score correlation
12 versions of loss curves but no analysis of whether lower loss actually correlates with higher eval scores. Key data points:
- v8: loss 0.11, GAME 0.09 (20s)
- v9: loss 0.14, GAME 0.20 (100s, different timeout)
- v10: loss 0.19, GAME 0.22
- v11: loss 0.17, GAME 0.23

Loss went UP from v8→v10 (0.11→0.19) while GAME went UP (0.09→0.22). The relationship is not straightforward because:
1. Eval config changed (timeout 600s→7200s)
2. Data diversity increased (more envs = higher loss is expected)
3. Sample sizes differed

---

## 9. Recommendations for v1+ on New Machine

### Immediate (v1)
1. Train with inherited data as-is to validate pipeline
2. Eval GAME + NAVWORLD with 100 samples each, timeout=7200s
3. Establish comparable baseline

### Short-term (v2-v3)
4. DPO experiment on NAVWORLD (241 pairs) — validate pipeline, measure delta vs SFT-only
5. Rebalance data mix: reduce LGC-v2/PRINT to 15% each, boost NAVWORLD/GAME/SWE-SYNTH
6. DDB refresh for fresh high-score samples

### Medium-term (v4+)
7. DPO on GAME (589 pairs) for hard games
8. seq=8192 for SWE-SYNTH coverage
9. Systematic A/B testing of data mix ratios
10. Leaderboard gap analysis framework

### Process improvements
- One variable per experiment
- 100+ samples per eval
- Eval ALL locally-testable envs every version
- Document hypothesis before training
- Track gap-to-target per environment per iteration
