#!/bin/bash
# GAME bot testing tool — upload, test, check results
# Usage:
#   ./scripts/game/test_bots.sh upload        # Upload all bot files to GPU
#   ./scripts/game/test_bots.sh test [GAME]   # Run 3-game test (all or specific)
#   ./scripts/game/test_bots.sh status        # Check results
#   ./scripts/game/test_bots.sh analyze GAME  # Read full detail for a game
#   ./scripts/game/test_bots.sh all           # Upload + test all + wait + status

FORGE=".venv/bin/python3 -m forge rental"
GPU_DIR="/root/project/scripts/game"
GAMES="goofspiel leduc_poker liars_dice gin_rummy othello hex clobber"

upload() {
    echo "=== Uploading bot files to GPU ==="
    for f in scripts/game/*.py; do
        $FORGE upload "$f" "$GPU_DIR/$(basename $f)" 2>&1 | tail -1
    done
    $FORGE upload scripts/game_bots.py "/root/project/scripts/game_bots.py" 2>&1 | tail -1
    echo "Done."
}

test_game() {
    local game=$1
    $FORGE exec "PYTHONPATH=$GPU_DIR OPENSPIEL_DIR=/root/affinetes/environments/openspiel nohup python3 $GPU_DIR/test3.py $game > $GPU_DIR/d3_${game}.txt 2>&1 & echo '$game started'" 2>&1 | grep -v Connecting
}

test_all() {
    echo "=== Testing all 7 games (3 games each, async) ==="
    for g in $GAMES; do
        test_game "$g"
    done
}

status() {
    echo "=== Results ==="
    $FORGE exec "for g in $GAMES; do r=\$(grep '^RESULT' $GPU_DIR/d3_\${g}.txt 2>/dev/null); echo \"\$g: \${r:-running}\"; done" 2>&1 | grep -v Connecting
}

analyze() {
    local game=$1
    echo "=== $game detail ==="
    $FORGE exec "cat $GPU_DIR/d3_${game}.txt 2>/dev/null" 2>&1 | grep -v Connecting
}

case "${1:-}" in
    upload) upload ;;
    test)
        if [ -n "${2:-}" ]; then test_game "$2"
        else test_all; fi ;;
    status) status ;;
    analyze) analyze "${2:?Usage: test_bots.sh analyze GAME}" ;;
    all) upload; test_all ;;
    *) echo "Usage: $0 {upload|test [GAME]|status|analyze GAME|all}" ;;
esac
