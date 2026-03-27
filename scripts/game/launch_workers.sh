#!/bin/bash
cd /root/project 2>/dev/null || cd ~/project
pkill -f orchestrate_v11 2>/dev/null
pkill -f generate_v11 2>/dev/null
sleep 2

CPUS=${1:-100}
# 40% gin, 30% hex, 30% othello
GIN=$((CPUS * 40 / 100))
HEX=$((CPUS * 30 / 100))
OTH=$((CPUS - GIN - HEX))

echo "Launching $GIN gin + $HEX hex + $OTH othello workers"

for i in $(seq 1 $GIN); do
    seed=$((RANDOM * 1000 + i * 7))
    PYTHONPATH=scripts/game nohup python3 scripts/game/generate_v11.py --game gin_rummy -n 2000 --start-seed $seed -o data/v11/v11_gin_rummy_${HOSTNAME}_w${i}.jsonl > /dev/null 2>&1 &
done

for i in $(seq 1 $HEX); do
    seed=$((RANDOM * 1000 + i * 13))
    PYTHONPATH=scripts/game nohup python3 scripts/game/generate_v11.py --game hex -n 2000 --start-seed $seed -o data/v11/v11_hex_${HOSTNAME}_w${i}.jsonl > /dev/null 2>&1 &
done

for i in $(seq 1 $OTH); do
    seed=$((RANDOM * 1000 + i * 17))
    PYTHONPATH=scripts/game nohup python3 scripts/game/generate_v11.py --game othello -n 2000 --start-seed $seed -o data/v11/v11_othello_${HOSTNAME}_w${i}.jsonl > /dev/null 2>&1 &
done

sleep 3
echo "Workers: $(ps aux|grep generate_v11|grep -v grep|wc -l)"
