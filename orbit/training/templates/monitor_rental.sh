#!/usr/bin/env bash
# CLI rental monitor: GPU + training process + loss.
# Used by: orbit rental monitor
echo "=== GPU ==="
nvidia-smi --query-gpu=index,utilization.gpu,memory.used,memory.total \
    --format=csv,noheader 2>/dev/null || echo "No GPU data"

echo "=== Training ==="
if pgrep -f 'train_sft.py|swift' > /dev/null 2>&1; then
    echo "Status: RUNNING"
else
    echo "Status: STOPPED"
fi

echo "=== Progress ==="
screen -S training -X hardcopy /tmp/screen_out 2>/dev/null
grep -oP '\d+/\d+.*it\]' /tmp/screen_out 2>/dev/null | tail -1 || echo "no progress yet"

echo "=== Loss ==="
python3 -c "
import json, glob
files = sorted(glob.glob('/root/checkpoints/checkpoint-*/trainer_state.json'))
if not files:
    print('No checkpoint yet')
else:
    for e in json.load(open(files[-1])).get('log_history', [])[-5:]:
        if 'loss' in e or 'train_loss' in e:
            step = e.get('step', '?')
            loss = e.get('loss', e.get('train_loss', '?'))
            print(f'  step {step}: loss={loss}')
" 2>/dev/null || echo "no loss data"
