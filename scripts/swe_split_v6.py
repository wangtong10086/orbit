#!/usr/bin/env python3
"""Split remaining v6 tasks into a second batch file for concurrent distillation."""
import json, re

# Get instance_ids from log (all attempted)
log_ids = set()
with open('/root/swe_distill_v6_go.log') as f:
    for line in f:
        m = re.match(r'\[(\d+)/337\]\s+(\S+)', line)
        if m:
            log_ids.add(m.group(2))

# Get all tasks
all_tasks = []
for line in open('/root/swe_batch_go_v6.jsonl'):
    all_tasks.append(json.loads(line))

# Remaining = not yet attempted
remaining = [t for t in all_tasks if t['instance_id'] not in log_ids]
print(f'Attempted: {len(log_ids)}, Remaining: {len(remaining)}')

# Write second half to new file for concurrent process
mid = len(remaining) // 2
half2 = remaining[mid:]
with open('/root/swe_batch_go_v6b.jsonl', 'w') as f:
    for t in half2:
        f.write(json.dumps(t) + '\n')
print(f'Wrote /root/swe_batch_go_v6b.jsonl with {len(half2)} tasks')
