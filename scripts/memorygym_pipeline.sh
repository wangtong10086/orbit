#!/bin/bash
# MemoryGym v4 data pipeline — end-to-end generation
# Usage: bash scripts/memorygym_pipeline.sh [target_count] [workers]
#
# Generates mixed-tier trajectories, splits into per-event samples,
# balances distribution, validates quality, and syncs to canonical.
#
# Example:
#   bash scripts/memorygym_pipeline.sh 20000 4

set -euo pipefail

TARGET=${1:-20000}
WORKERS=${2:-1}
TIMESTAMP=$(date +%Y%m%dT%H%M)

# Directories
DATA_DIR="data"
CANONICAL="data/canonical/memorygym.jsonl"
WORK_DIR="data/memorygym_v4_${TIMESTAMP}"
mkdir -p "$WORK_DIR"

# Calculate seeds needed: ~20 events per trajectory (lite~18, standard~25, hard~67)
# Mixed tiers average ~30 events per trajectory
# Need TARGET / 30 * 1.5 (oversample for balanced downsampling) / 10 (templates)
EVENTS_PER_TRAJ=30
OVERSAMPLE=2.0
SEEDS=$(python3 -c "import math; print(max(10, math.ceil($TARGET / $EVENTS_PER_TRAJ * $OVERSAMPLE / 10)))")
echo "=== MemoryGym v4 Pipeline ==="
echo "  Target: $TARGET samples"
echo "  Seeds: $SEEDS per template (10 templates)"
echo "  Workers: $WORKERS"
echo "  Output: $WORK_DIR"
echo ""

# Step 1: Generate trajectories (mixed tiers)
RAW="$WORK_DIR/trajectories.jsonl"
echo "--- Step 1: Generate trajectories (mixed tiers) ---"
python3 scripts/memorygym_hybrid_gen.py \
    -o "$RAW" \
    --seeds "$SEEDS" \
    --tier-mix \
    -j "$WORKERS" \
    2>&1

echo ""

# Step 2: Split + balance
SPLIT="$WORK_DIR/split_balanced.jsonl"
echo "--- Step 2: Split and balance to $TARGET samples ---"
python3 scripts/memorygym_split_events.py \
    -i "$RAW" \
    -o "$SPLIT" \
    --target "$TARGET" \
    --balance \
    2>&1

echo ""

# Step 3: Validate
echo "--- Step 3: Validate ---"
python3 -c "
import json

samples = [json.loads(l) for l in open('$SPLIT')]
print(f'Total samples: {len(samples)}')

# Token length check
tokens = [sum(len(m.get(\"content\",\"\")) for m in s[\"messages\"])//4 for s in samples]
tokens.sort()
over_32k = sum(1 for t in tokens if t > 32000)
print(f'Token: median={tokens[len(tokens)//2]:,}, max={tokens[-1]:,}, >32K={over_32k}')

# Distribution check
by_type = {}
for s in samples:
    t = s['event_type']
    by_type[t] = by_type.get(t, 0) + 1
for t, c in sorted(by_type.items()):
    print(f'  {t}: {c} ({c/len(samples)*100:.1f}%)')

# Quality checks
questions = [s for s in samples if s['event_type'] == 'question']
no_search = 0
for s in questions:
    asst = [m for m in s['messages'] if m['role']=='assistant' and m['content'].strip()!='OK.']
    if not any('memory_search' in m['content'] for m in asst):
        no_search += 1
print(f'Questions without search: {no_search}/{len(questions)}')

# Format check
bad_format = 0
for s in samples:
    for m in s['messages']:
        if 'ANSWER_SUBMITTED' in m.get('content','') and not m['content'].startswith('Tool results:'):
            bad_format += 1
print(f'Bad submit_answer format: {bad_format}')

# System prompt check
import hashlib
prompts = set()
for s in samples:
    sp = s['messages'][0]['content'] if s['messages'] else ''
    prompts.add(hashlib.md5(sp.encode()).hexdigest())
print(f'Unique system prompts: {len(prompts)} (should be 1 per tier)')

if over_32k > 0 or no_search > 0 or bad_format > 0:
    print('\n*** VALIDATION FAILED ***')
    exit(1)
else:
    print('\n*** ALL CHECKS PASSED ***')
"

echo ""

# Step 4: Copy to canonical
echo "--- Step 4: Deploy to canonical ---"
cp "$SPLIT" "$CANONICAL"
echo "Copied to $CANONICAL"

# Count
FINAL_COUNT=$(wc -l < "$CANONICAL")
echo "Final count: $FINAL_COUNT"
echo ""
echo "=== Pipeline complete ==="
echo "  Canonical: $CANONICAL ($FINAL_COUNT entries)"
echo "  Working dir: $WORK_DIR"
echo ""
echo "Next: run 'forge data canonical-upload --env MEMORYGYM' to sync to HF"
