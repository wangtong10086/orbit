#!/usr/bin/env python3
"""Check Go task coverage: how many Go tasks in pool vs attempted."""
import json, glob, re

# All instance_ids from batch files
batched = set()
for f in glob.glob("/root/swe_batch_*.jsonl"):
    for line in open(f):
        try:
            t = json.loads(line)
            batched.add(t["instance_id"])
        except: pass

# All instance_ids from output files (successes)
output = set()
for f in glob.glob("/root/real_distill_v*.jsonl"):
    for line in open(f):
        try:
            output.add(json.loads(line)["instance_id"])
        except: pass

# All attempted from logs
attempted = set()
for logf in glob.glob("/root/swe_distill_v*.log"):
    with open(logf) as fh:
        for line in fh:
            m = re.match(r'\[(?:R?\d+/\d+)\]\s+(\S+)', line)
            if m:
                attempted.add(m.group(1))

combined = batched | attempted | output

# Check how many Go tasks exist in v8 prep (which downloaded all tasks)
# The prep_nongo script just ran and found pool=2870
# Let's count Go tasks we know about from batch files
go_batched = set()
non_go_batched = set()
for f in glob.glob("/root/swe_batch_*.jsonl"):
    for line in open(f):
        try:
            t = json.loads(line)
            lang = t.get("repo_language", "").lower()
            if lang == "go":
                go_batched.add(t["instance_id"])
            else:
                non_go_batched.add(t["instance_id"])
        except: pass

print(f"=== Coverage Report ===")
print(f"Total batched IDs: {len(batched)}")
print(f"  Go batched: {len(go_batched)}")
print(f"  Non-Go batched: {len(non_go_batched)}")
print(f"Output IDs (success): {len(output)}")
print(f"Attempted IDs (from logs): {len(attempted)}")
print(f"Combined unique known: {len(combined)}")
print(f"")
print(f"Pool total: 2870 (from prep_nongo)")
print(f"Estimated Go in pool (56%): ~1607")
print(f"Go tasks we've batched: {len(go_batched)}")
print(f"Go coverage: {len(go_batched)}/~1607 = {len(go_batched)*100//1607}%")
print(f"Unbatched Go (estimate): ~{1607 - len(go_batched)}")
