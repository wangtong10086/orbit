# Scoring Algorithm & Competition Strategy Analysis

## Scoring Algorithm Core (4 Stages)

### Stage 1: Data Collection
- Average score per miner per environment
- **Completeness >= 90%** required (completed / total >= 0.9)
- Anti-copying threshold: `threshold = avg + z_score * SE + improvement`

### Stage 2: Pareto Anti-Copying
- Sorted by `first_block` (deployment time), earlier miners have priority
- New models must **statistically significantly** exceed existing models, not just be slightly better
- Dominated miners are directly filtered out

### Stage 3: Subset Scoring
- **`MAX_LAYERS = 1`**: only calculates subsets of **all environments**
- Uses **geometric mean** (any zero score drags down the total)
- Rank decay `decay_factor=0.5`: #1 = 1x, #2 = 0.5x, #3 = 0.25x

### Stage 4: Weight Normalization
- Miners below 1% weight are zeroed out
- Total normalized to 1.0

## Key Parameters

| Parameter | Value | Meaning |
|-----------|-------|---------|
| Z_SCORE (default) | 1.5 | 87% confidence |
| Z_SCORE (GAME) | 1.0 | Easier to exceed |
| Z_SCORE (PRINT/SWE) | 2.0 | Harder to exceed |
| MIN_IMPROVEMENT | 0.02 | Must improve by at least 2% |
| DECAY_FACTOR | 0.5 | Lower rank = faster weight decay |
| MIN_COMPLETENESS | 0.9 | Completeness threshold |
| Rate limit exemption | 14400 blocks (~48h) | New model protection period |

## Strategic Implications

1. **Must develop all-around**: geometric mean = weakest link determines the ceiling
2. **GAME is easier to break through**: z_score=1.0, lower statistical threshold than other environments
3. **PRINT/SWE-SYNTH hard to break through**: z_score=2.0, requires larger advantage
4. **Early deployment has an advantage**: Pareto sorting by time
5. **48-hour evaluation cycle**: must wait at least 2 days after deployment to see results

## Current Top Model Analysis

| Rank | GAME | LGC-v2 | LIVEWEB | NAVWORLD | PRINT | SWE-SYNTH |
|------|------|--------|---------|----------|-------|-----------|
| #1 (116) | 30 | 82 | 25 | 10 | 73 | 38 |
| #2 (120) | 47 | 91 | 26 | 6 | 79 | 30 |
| #3 (45) | 41 | 90 | 28 | 7 | 83 | 26 |

- #1 wins through **all-around balance** (no weaknesses)
- #2 highest GAME but weak NAVWORLD/SWE-SYNTH
- LGC-v2 and PRINT have little differentiation (80-91), GAME and SWE-SYNTH have large variance

## Deployment Pipeline
1. LoRA → merge → upload to HuggingFace
2. Deploy on Chutes AI (SGLang, 4×H200)
3. On-chain commit (`af commit --repo --revision --chute-id`)
4. Wait 48h for scoring
