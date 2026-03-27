# Short-term Memory

## 2026-03-27: v3 dataset — per-event split, ready for training

### What was done
1. Deep audit found 6 critical issues in v1 data (1400 entries)
2. Fixed generator: redaction matching eval, Edit 99.6% (was 65.5%), reasoning chains
3. Generated 1500 trajectories (v2) — but median 41K tokens, 87% truncated at seq=32K
4. **Key insight**: eval does `del messages[1:]` between events → each event is independent
5. Split trajectories at redaction boundaries → 40K per-event samples → downsampled to 5000
6. v3 result: 5000 entries, median 1.8K tokens, 0% truncation, matches eval context exactly

### Current state
- **Canonical**: `data/canonical/memorygym.jsonl` — 5000 per-event samples
- **HF**: synced to `monokoco/affine-sft-data/memorygym.jsonl`
- **Generator**: `scripts/memorygym_hybrid_gen.py` (fixed Edit matching)
- **Splitter**: `scripts/memorygym_split_events.py` (trajectory → per-event)
- **Full trajectories backup**: `data/memorygym_v2_*.jsonl` (4 files, 1500 total)

### If more data needed
- Can generate more trajectories on m3 (128 cores) and split
- Current 1500 trajectories → 40K events, only used 5000 (12.5%)
- Can upsample to 10K-20K from existing pool without regeneration

### On resume
- MemoryGym priority raised, approaching leaderboard inclusion
- Monitor eval results after first training with v3 data
- If SFT ceiling hit again, escalate GRPO discussion with user
