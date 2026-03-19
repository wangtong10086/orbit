# Data Quality Deep Analysis — 2026-03-19

## Root Cause Analysis: Why Each Environment is Weak

### 1. SWE-SYNTH (expect 10-25, competitors 30-43)

**Root cause: 70.7% of training data gets TRUNCATED at seq=8192.**

| seq_len | Entries fit | Coverage |
|---------|-----------|---------|
| 4096 | 24 | 2.4% |
| 8192 | 288 | 29.3% |
| **16384** | **916** | **93.2%** |
| 32768 | 983 | 100% |

v2 trained at seq=8192 → only 29.3% of 983 entries are seen complete. The other 70.7% are truncated mid-debugging — model learns to START solving but never sees the FINISH.

**Fix**: Either increase seq_len to 16384 (93.2% coverage) or filter to only entries fitting seq=8192 (288 entries). Recommend seq=16384 — more data + complete solutions.

### 2. NAVWORLD (expect 5-8, competitors 16-24)

**Root cause: 5 template patterns, not data volume.**

- Exactly 5 unique tool-call sequences across 2248 entries
- Each template has ~450 copies with only city name variation
- 10 origin cities, ~25 destinations
- Plan length std=160 chars (extremely narrow)

Model memorizes 5 recipes. When diverse queries arrive, it pattern-matches to the wrong recipe.

**Fix (in progress)**: D8 Phase 1 adds 8 new diverse query types (400 entries). Downsample existing 5 templates from 2248→1000 (200 per template). Final: 1000 old + 400 new = 1400 entries with 13 query types.

### 3. GAME (expect 25-35, competitors 40-51)

**Root cause: Low think diversity + oversampled solved games.**

| Game | Entries | Unique thinks | Issue |
|------|---------|---------------|-------|
| goofspiel | 1050 | 8419 | Solved (bid=prize), oversampled |
| gin_rummy | 780 | 266 | 83.6% draws, shallow strategy |
| leduc_poker | 428 | 738 | Decent but no fold examples |
| liars_dice | 333 | **4** | Near-zero learning value |
| hex | 190 | 85 | Zero-tier, all wins |
| clobber | 123 | 50 | Zero-tier, all wins |
| othello | 12 | 84 | Too few entries |

**Fix**: Filter to high-signal entries:
- Downsample goofspiel 1050→500 (solved, diminishing returns)
- Remove liars_dice with ≤1 unique think (91 entries)
- Cap zero-tier games at 100 each
- Result: 2916→2154 entries with higher signal density

### 4. LIVEWEB (expect 15-20, competitors 14-19)

**Root cause: Upstream data constraint.** Only 18 entries <16K chars. Can't improve without upstream compression. Acceptable as safety net.

## v3 Quality-Filtered Data Plan

### Option A: seq=8192 (current)

| Env | v2 Count | v3 Filtered | Change |
|-----|----------|-------------|--------|
| GAME | 2641 | 2154 | -487 (removed low-signal) |
| NAVWORLD | 2248 | 1400 | -848 (downsample + D8 diversity) |
| SWE-SYNTH | 983 | 288 | -695 (only seq-compatible) |
| LIVEWEB | 18 | 18 | — |
| **Total** | **5890** | **3860** | **-2030** |

### Option B: seq=16384 (recommended)

| Env | v2 Count | v3 Filtered | Change |
|-----|----------|-------------|--------|
| GAME | 2641 | 2154 | -487 |
| NAVWORLD | 2248 | 1400 | -848 |
| SWE-SYNTH | 983 | 916 | -67 (93% coverage) |
| LIVEWEB | 18 | 18 | — |
| **Total** | **5890** | **4488** | **-1402** |

## Key Insight: Less Data, Higher Quality

v3 has fewer entries than v2, but:
- **Zero truncated SWE-SYNTH** → model sees complete solutions
- **13 NAVWORLD query types** instead of 5 → breaks template ceiling
- **No low-signal GAME data** → every entry teaches strategy
- **Balanced distribution** → no single game dominates

This follows the "rejection sampling + quality filtering" approach used by DeepSeek-R1 and Qwen-series models: curate aggressively, train less but better.
