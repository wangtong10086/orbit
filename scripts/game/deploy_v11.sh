#!/bin/bash
# Deploy v11 generation across all 4 machines
# Usage: bash scripts/game/deploy_v11.sh

set -e

SCRIPTS="scripts/game/generate_v11.py scripts/game/orchestrate_v11.sh scripts/game/goofspiel_bot.py scripts/game/leduc_poker_bot.py scripts/game/gin_rummy_bot.py scripts/game/mcts_helper.py"

# Machine configs: name, ssh_target, max_cpus
MACHINES=(
    "m1|forge_m1|120"
    "m2|forge_m2|120"
    "work1|work1|64"
    "work2|work2|64"
)

upload_forge() {
    local name=$1 target=$2
    echo "=== Uploading to $name ==="
    for f in $SCRIPTS; do
        .venv/bin/python3 -m forge rental -m "$target" upload "$f" "/root/project/$f" 2>&1 | grep -v protocol
    done
    .venv/bin/python3 -m forge rental -m "$target" exec "rm -rf /root/project/scripts/game/__pycache__; mkdir -p /root/project/data/v11" 2>&1 | tail -1
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
    .venv/bin/python3 -m forge rental -m "$target" exec \
        "cd /root/project && nohup bash scripts/game/orchestrate_v11.sh $name $cpus > /tmp/v11_orchestrator.log 2>&1 & echo 'orchestrator started'" 2>&1 | tail -1
}

start_ssh() {
    local name=$1 cpus=$2
    echo "=== Starting on $name ($cpus CPUs) ==="
    ssh "$name" "cd /root/project && nohup bash scripts/game/orchestrate_v11.sh $name $cpus > /tmp/v11_orchestrator.log 2>&1 & echo 'orchestrator started'"
}

# Kill existing v11 processes on all machines
echo "Killing existing v11 processes..."
.venv/bin/python3 -m forge rental exec "pkill -f generate_v11 2>/dev/null; pkill -f orchestrate_v11 2>/dev/null; echo 'm1 clean'" 2>&1 | tail -1
.venv/bin/python3 -m forge rental -m m2 exec "pkill -f generate_v11 2>/dev/null; pkill -f orchestrate_v11 2>/dev/null; echo 'm2 clean'" 2>&1 | tail -1
ssh work1 "pkill -f generate_v11 2>/dev/null; pkill -f orchestrate_v11 2>/dev/null; echo 'work1 clean'" 2>&1
ssh work2 "pkill -f generate_v11 2>/dev/null; pkill -f orchestrate_v11 2>/dev/null; echo 'work2 clean'" 2>&1

# Upload to all machines
upload_forge "m1" "m1"
upload_forge "m2" "m2"
upload_ssh "work1"
upload_ssh "work2"

# Start orchestrators
start_forge "m1" "m1" 120
start_forge "m2" "m2" 120
start_ssh "work1" 64
start_ssh "work2" 64

echo ""
echo "=== All 4 orchestrators started ==="
echo "Total CPUs: 368 (m1:120 + m2:120 + work1:64 + work2:64)"
echo "Monitor: ssh [machine] 'tail -f /tmp/v11_orchestrator.log'"
echo "Check:   ssh [machine] 'wc -l /root/project/data/v11/v11_*.jsonl'"
