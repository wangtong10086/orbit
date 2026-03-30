#!/bin/bash
# Collect v11 data from all machines to local, with dedup
# Run periodically: bash scripts/game/collect_v11.sh
# Or in loop: while true; do bash scripts/game/collect_v11.sh; sleep 300; done

LOCALDIR="data/v11"
mkdir -p "$LOCALDIR"

echo "[$(date +%H:%M:%S)] Collecting v11 data..."

# Collect from each machine
for machine in m1 m2; do
    echo "  $machine..."
    .venv/bin/python3 -m forge remote -m "$machine" exec "cat /root/project/data/v11/v11_*.jsonl 2>/dev/null" >> "${LOCALDIR}/raw_${machine}.jsonl.tmp" 2>/dev/null
    if [ -s "${LOCALDIR}/raw_${machine}.jsonl.tmp" ]; then
        mv "${LOCALDIR}/raw_${machine}.jsonl.tmp" "${LOCALDIR}/raw_${machine}.jsonl"
        echo "    $(wc -l < ${LOCALDIR}/raw_${machine}.jsonl) lines"
    else
        rm -f "${LOCALDIR}/raw_${machine}.jsonl.tmp"
        echo "    no data"
    fi
done

for machine in work1 work2; do
    echo "  $machine..."
    ssh "$machine" "cat /root/project/data/v11/v11_*.jsonl 2>/dev/null" >> "${LOCALDIR}/raw_${machine}.jsonl.tmp" 2>/dev/null
    if [ -s "${LOCALDIR}/raw_${machine}.jsonl.tmp" ]; then
        mv "${LOCALDIR}/raw_${machine}.jsonl.tmp" "${LOCALDIR}/raw_${machine}.jsonl"
        echo "    $(wc -l < ${LOCALDIR}/raw_${machine}.jsonl) lines"
    else
        rm -f "${LOCALDIR}/raw_${machine}.jsonl.tmp"
        echo "    no data"
    fi
done

# Merge and dedup
echo "  Merging..."
cat ${LOCALDIR}/raw_*.jsonl 2>/dev/null > "${LOCALDIR}/raw_all.jsonl.tmp"

python3 -c "
import json

seen = set()
games = {}
valid = 0
errors = 0

with open('${LOCALDIR}/raw_all.jsonl.tmp') as fin, open('${LOCALDIR}/v11_combined.jsonl', 'w') as fout:
    for line in fin:
        try:
            e = json.loads(line)
            tid = e.get('task_id')
            if tid in seen:
                continue
            seen.add(tid)
            # Validate: assistant messages are pure numbers
            ok = True
            for m in e.get('messages', []):
                if m.get('role') == 'assistant':
                    if not m['content'].strip().isdigit():
                        ok = False
                        break
            if ok:
                fout.write(line)
                valid += 1
                g = e.get('game', '?')
                games[g] = games.get(g, 0) + 1
            else:
                errors += 1
        except:
            errors += 1

print(f'  Valid: {valid}, Errors: {errors}, Dupes removed: {len(seen) - valid if valid < len(seen) else 0}')
for g in ['goofspiel','leduc_poker','liars_dice','gin_rummy','hex','othello','clobber']:
    target = {'goofspiel':2000,'leduc_poker':2000,'liars_dice':5000,'gin_rummy':2000,'hex':6500,'othello':5000,'clobber':10000}.get(g,0)
    cur = games.get(g, 0)
    pct = cur*100//target if target else 0
    print(f'    {g}: {cur}/{target} ({pct}%)')
print(f'  Total: {valid}')
"

rm -f "${LOCALDIR}/raw_all.jsonl.tmp"
echo "[$(date +%H:%M:%S)] Done. File: ${LOCALDIR}/v11_combined.jsonl"
