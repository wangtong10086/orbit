# Scoring Mechanism — Deep Dive

> Status: Reference note
> Authority: Non-normative
> Last reviewed: 2026-04-04
> Use this file for background and deep analysis, not as the primary source of truth.


Source: `affine-cortex/affine/src/scorer/` (read 2026-03-18)

## 4-Stage Algorithm

### Stage 1: Data Collection
- Collect per-env average scores from DynamoDB `sample_results`
- Completeness check: sample_count / total_tasks >= threshold (0.8-0.9)
- Incomplete environments are excluded for that miner

### Stage 2: Pareto Anti-Copy Filter
- If miner B cannot beat miner A on any environment subset, and A registered earlier, B is filtered
- Threshold: `required_score = prior_score + gap`, where gap = z * SE
- SE = sqrt(p * (1-p) / n) — more samples = smaller gap = easier to beat
- **Per-env z_score overrides**: GAME=1.0 (easier), PRINT=2.0 (harder), SWE-SYNTH=2.0 (harder)

### Stage 3: Subset Scoring (most important for strategy)

**Subset generation**:
- All combinations: L1 (single envs), L2 (pairs), L3 (triples)... up to L(n)
- MAX_LAYERS=6: if n > 6 envs, skip lowest layers (e.g., 7 envs → evaluate L2-L7, skip L1)

**Layer weights**: `weight = N * 2^(layer_index)` where layer_index starts from 0
- With 6 active envs: L1=6, L2=12, L3=24, L4=48, L5=96, L6=192
- L6 is **32x** more important than L1
- **Implication**: the single full-coverage subset (all envs combined) has enormous weight

**Per-subset scoring**:
1. For each subset, calculate smoothed geometric mean of env scores per miner
2. Rank miners by score within that subset
3. Apply decay: `adjusted = score * 0.5^(rank-1)` — rank 2 gets 50%, rank 3 gets 25%
4. Distribute subset weight proportionally to adjusted scores

**Geometric mean smoothing**: `epsilon = 0.1`
- Formula: GM = ((v1+0.1) * (v2+0.1) * ...)^(1/n) - 0.1
- Effect: zero score becomes 0.1 before calculation, not 0
- A true zero in 1 of 6 envs: (0.1 * 1.1^5)^(1/6) - 0.1 ≈ 0.37 (not zero!)
- But still much worse than scoring even 0.05 (which becomes 0.15)

### Stage 4: Weight Normalization
- Sum all subset weight contributions per miner
- Apply min threshold (1% = 0.01) — below → set to 0, redistributed to UID 0
- Normalize to sum=1.0

## Strategic Implications

### 1. Full coverage is king — but not for the reason you think
- L6 (all envs combined) has 32x the weight of L1 (single env)
- Being competitive in the all-envs-combined subset is the single most important thing
- But epsilon smoothing means a zero doesn't kill you completely

### 2. Ranking matters as much as absolute score
- DECAY_FACTOR=0.5: rank 2 gets half of rank 1's weight share per subset
- Improving from rank 3 → rank 2 in a subset doubles your weight from that subset
- **Implication**: better to be rank 2 everywhere than rank 1 on half + rank 5 on half

### 3. "Barely scoring" vs "zero" is huge
- Score 0.0 in an env → smoothed to 0.1 → geometric mean takes a hit
- Score 0.05 → smoothed to 0.15 → 50% better input to geometric mean
- Even tiny non-zero scores in weak envs have outsized impact on the total

### 4. Anti-copy filter favors established miners
- Earlier registration = natural advantage
- New miners must clearly exceed, not just match
- GAME z=1.0 (easier to differentiate), PRINT/SWE-SYNTH z=2.0 (harder)

## Decision Framework for Data Mix

Given the scoring mechanism, the optimal data mix should:
1. **Ensure non-zero scores in ALL environments** — the smoothed geometric mean still punishes zeros heavily
2. **Maximize rank across subsets** — decay_factor=0.5 means each rank improvement ~doubles weight
3. **Prioritize environments where we can jump ranks** — going from rank 5→3 in an env improves many subsets
4. **Balance over dominance** — being rank 2 in all 6 envs > rank 1 in 3 + rank 6 in 3
