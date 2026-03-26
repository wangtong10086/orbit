#!/bin/bash
# v11 GAME data generation orchestrator
# Automatically manages workers across machines, refills when done.
#
# Usage: bash scripts/game/orchestrate_v11.sh [machine] [max_cpus]
# Example: bash scripts/game/orchestrate_v11.sh m1 120
#          bash scripts/game/orchestrate_v11.sh work1 64
#
# Targets (from competitive analysis):
#   goofspiel: 2000, leduc: 2000, liars: 5000
#   gin: 2000, hex: 6500, othello: 5000, clobber: 10000
# Total: ~32500

MACHINE=${1:-local}
MAX_CPUS=${2:-100}
DATADIR="data/v11"
SCRIPTDIR="scripts/game"
LOGDIR="/tmp/v11_logs"

# Per-game targets
declare -A TARGETS
TARGETS[goofspiel]=2000
TARGETS[leduc_poker]=2000
TARGETS[liars_dice]=5000
TARGETS[gin_rummy]=2000
TARGETS[hex]=6500
TARGETS[othello]=5000
TARGETS[clobber]=10000

# Workers per game (proportional to target, heavy games get more)
declare -A WORKERS
WORKERS[goofspiel]=2
WORKERS[leduc_poker]=2
WORKERS[liars_dice]=8
WORKERS[gin_rummy]=8
WORKERS[hex]=20
WORKERS[othello]=15
WORKERS[clobber]=20

# Batch size per worker (how many attempts before checking)
declare -A BATCH
BATCH[goofspiel]=500
BATCH[leduc_poker]=500
BATCH[liars_dice]=300
BATCH[gin_rummy]=200
BATCH[hex]=200
BATCH[othello]=200
BATCH[clobber]=200

mkdir -p "$DATADIR" "$LOGDIR"

# Scale workers to fit MAX_CPUS
total_workers=0
for g in "${!WORKERS[@]}"; do
    total_workers=$((total_workers + ${WORKERS[$g]}))
done

if [ $total_workers -gt $MAX_CPUS ]; then
    echo "Scaling workers from $total_workers to fit $MAX_CPUS CPUs"
    for g in "${!WORKERS[@]}"; do
        WORKERS[$g]=$(( ${WORKERS[$g]} * $MAX_CPUS / $total_workers ))
        [ ${WORKERS[$g]} -lt 1 ] && WORKERS[$g]=1
    done
fi

echo "=== v11 Orchestrator: $MACHINE ($MAX_CPUS CPUs) ==="
for g in goofspiel leduc_poker liars_dice gin_rummy hex othello clobber; do
    echo "  $g: target=${TARGETS[$g]}, workers=${WORKERS[$g]}, batch=${BATCH[$g]}"
done

count_entries() {
    local game=$1
    local total=0
    for f in ${DATADIR}/v11_${game}_*.jsonl; do
        if [ -f "$f" ]; then
            c=$(wc -l < "$f" 2>/dev/null || echo 0)
            total=$((total + c))
        fi
    done
    echo $total
}

run_worker() {
    local game=$1
    local worker_id=$2
    local seed=$((RANDOM * 1000 + worker_id * 10000 + $(date +%s) % 100000))
    local batch=${BATCH[$game]}
    local outfile="${DATADIR}/v11_${game}_${MACHINE}_w${worker_id}.jsonl"
    local logfile="${LOGDIR}/${game}_${MACHINE}_w${worker_id}.log"

    PYTHONPATH=${SCRIPTDIR} OPENSPIEL_DIR=/root/affinetes/environments/openspiel \
        python3 ${SCRIPTDIR}/generate_v11.py \
        --game "$game" -n "$batch" --start-seed "$seed" -o "$outfile" \
        > "$logfile" 2>&1
}

# Main loop: for each game, maintain target number of workers
while true; do
    all_done=true

    for game in goofspiel leduc_poker liars_dice gin_rummy hex othello clobber; do
        target=${TARGETS[$game]}
        current=$(count_entries "$game")

        if [ $current -ge $target ]; then
            continue
        fi
        all_done=false

        # Count running workers for this game
        running=$(ps aux | grep "generate_v11.*--game $game" | grep -v grep | wc -l)
        wanted=${WORKERS[$game]}
        need=$((wanted - running))

        if [ $need -gt 0 ]; then
            for i in $(seq 1 $need); do
                wid=$((RANDOM % 10000))
                run_worker "$game" "$wid" &
                echo "[$(date +%H:%M:%S)] Started $game worker $wid (current=$current/$target, running=$((running+i)))"
            done
        fi
    done

    if $all_done; then
        echo "=== ALL TARGETS REACHED ==="
        for game in goofspiel leduc_poker liars_dice gin_rummy hex othello clobber; do
            echo "  $game: $(count_entries $game)/${TARGETS[$game]}"
        done
        break
    fi

    # Status report every 60s
    echo ""
    echo "[$(date +%H:%M:%S)] === Status ==="
    total_running=$(ps aux | grep generate_v11 | grep -v grep | wc -l)
    echo "  Workers: $total_running"
    for game in goofspiel leduc_poker liars_dice gin_rummy hex othello clobber; do
        current=$(count_entries "$game")
        target=${TARGETS[$game]}
        pct=$((current * 100 / target))
        echo "  $game: $current/$target ($pct%)"
    done

    sleep 60
done
