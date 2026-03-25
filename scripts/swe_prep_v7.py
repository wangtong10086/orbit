#!/usr/bin/env python3
"""Prepare v7 batch: extract new Go tasks from R2 pool, excluding all previously attempted."""
import json, glob, subprocess, sys

# Collect all instance_ids from all output files (attempted tasks)
attempted = set()
for f in glob.glob("/root/real_distill_v*.jsonl"):
    for line in open(f):
        try:
            attempted.add(json.loads(line)["instance_id"])
        except:
            pass

# Collect all instance_ids from all batch files (tasks we've seen)
batched = set()
for f in glob.glob("/root/swe_batch_go_v*.jsonl"):
    for line in open(f):
        try:
            batched.add(json.loads(line)["instance_id"])
        except:
            pass

# Also check log files for attempted-but-not-output tasks
import re
for logf in glob.glob("/root/swe_distill_v*.log"):
    with open(logf) as fh:
        for line in fh:
            m = re.match(r'\[\d+/\d+\]\s+(\S+)', line)
            if m:
                attempted.add(m.group(1))
            m2 = re.match(r'\[R\d+/\d+\]\s+(\S+)', line)
            if m2:
                attempted.add(m2.group(1))

print(f"Total attempted (output+logs): {len(attempted)}")
print(f"Total batched: {len(batched)}")

# Download full R2 task list
import urllib.request
R2_BASE = "https://pub-7882418a56434a479bf9a7febd660b36.r2.dev/bugs"
# The tasks are individual files in R2, but we have the pool file
# Check if we have a local copy of the full pool
import os
pool_file = "/root/r2_go_pool.jsonl"
if not os.path.exists(pool_file):
    print("No pool file found. Extracting from R2...")
    # Use the expansion listing from affine-swe-infinite
    # For now, list what Go tasks exist that aren't in any batch
    print("ERROR: Need to fetch new tasks from R2 pool")
    sys.exit(1)

# Read pool and filter
new_tasks = []
for line in open(pool_file):
    t = json.loads(line)
    iid = t["instance_id"]
    lang = t.get("repo_language", "").lower()
    if lang == "go" and iid not in batched and iid not in attempted:
        new_tasks.append(t)

print(f"New Go tasks available: {len(new_tasks)}")

# Write v7 batch (split into 2 files for concurrent processing)
if new_tasks:
    mid = len(new_tasks) // 2
    with open("/root/swe_batch_go_v7a.jsonl", "w") as f:
        for t in new_tasks[:mid]:
            f.write(json.dumps(t) + "\n")
    with open("/root/swe_batch_go_v7b.jsonl", "w") as f:
        for t in new_tasks[mid:]:
            f.write(json.dumps(t) + "\n")
    print(f"Wrote v7a: {mid} tasks, v7b: {len(new_tasks) - mid} tasks")
else:
    print("No new tasks to process")
