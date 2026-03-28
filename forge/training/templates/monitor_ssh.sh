#!/usr/bin/env bash
# SSH training status monitor script.
# Output: structured status information for parsing by the CLI.
echo "=== Training Status ==="
if screen -list | grep -q training; then
    echo "Status: RUNNING"
    echo ""
    echo "=== Last 20 lines ==="
    tail -20 /root/training.log 2>/dev/null || echo "No log file"
    echo ""
    echo "=== GPU Usage ==="
    nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu \
        --format=csv,noheader 2>/dev/null || echo "No GPU"
    echo ""
    echo "=== Checkpoints ==="
    ls -lt /root/checkpoints/ 2>/dev/null | head -5 || echo "No checkpoints"
else
    echo "Status: NOT RUNNING"
    tail -20 /root/training.log 2>/dev/null || echo "No log file"
fi
