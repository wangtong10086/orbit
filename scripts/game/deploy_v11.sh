#!/bin/bash
# Deploy v11 generation across all machines (m1, m2, m3)
# Usage: bash scripts/game/deploy_v11.sh

SCRIPTS="scripts/game/generate_v11.py scripts/game/orchestrate_v11.sh scripts/game/goofspiel_bot.py scripts/game/leduc_poker_bot.py scripts/game/gin_rummy_bot.py scripts/game/mcts_helper.py"

upload_forge() {
    local name=$1 target=$2
    echo "=== Uploading to $name ==="
    for f in $SCRIPTS; do
        .venv/bin/python3 -m forge remote -m "$target" upload "$f" "/root/project/$f" 2>&1 | grep -v protocol
    done
    .venv/bin/python3 -m forge remote -m "$target" exec "rm -rf /root/project/scripts/game/__pycache__; mkdir -p /root/project/data/v11" 2>&1 | tail -1
}

upload_ssh() {
    local name=$1
    echo "=== Uploading to $name ==="
    ssh "$name" "mkdir -p /root/project/scripts/game /root/project/data/v11 /tmp/v11_logs"
    for f in $SCRIPTS; do
        scp "$f" "${name}:/root/project/$f" 2>/dev/null
    done
    ssh "$name" "rm -rf /root/project/scripts/game/__pycache__"
}

start_forge() {
    local name=$1 target=$2 cpus=$3
    echo "=== Starting on $name ($cpus CPUs) ==="
    .venv/bin/python3 -m forge remote -m "$target" exec \
        "cd /root/project && nohup bash scripts/game/orchestrate_v11.sh $name $cpus > /tmp/v11_orchestrator.log 2>&1 & echo 'orchestrator started'" 2>&1 | tail -1
}

start_ssh() {
    local name=$1 cpus=$2
    echo "=== Starting on $name ($cpus CPUs) ==="
    ssh "$name" "cd /root/project && nohup bash scripts/game/orchestrate_v11.sh $name $cpus > /tmp/v11_orchestrator.log 2>&1 & echo 'orchestrator started'"
}

# Kill existing v11 processes on all machines
echo "Killing existing v11 processes..."
for m in m1 m2 m3; do
    .venv/bin/python3 -m forge remote -m "$m" exec "pkill -f generate_v11 2>/dev/null; pkill -f orchestrate_v11 2>/dev/null; echo '$m clean'" 2>&1 | tail -1
done

# Upload to all machines
for m in m1 m2 m3; do
    upload_forge "$m" "$m"
done

# Start orchestrators — use all CPUs
for m in m1 m2 m3; do
    start_forge "$m" "$m" 120
done

echo ""
echo "=== All 3 orchestrators started ==="
echo "Total CPUs: 360 (m1:120 + m2:120 + m3:120)"
echo "Monitor: forge remote -m [m1|m2|m3] exec 'tail -30 /tmp/v11_orchestrator.log'"
echo "Check:   forge remote -m [m1|m2|m3] exec 'wc -l /root/project/data/v11/v11_*.jsonl'"
