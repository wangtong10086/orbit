#!/usr/bin/env python3
"""
SWE Pool Audit — ensure COMPLETE and NON-DUPLICATE coverage of the entire R2 pool.

This script:
1. Lists ALL tasks in R2 private pool
2. Checks which have been attempted (from all output + log files)
3. Generates batch files for ALL uncovered tasks, split by language
4. Reports exact coverage stats

Run on m2: python3 /root/swe_pool_audit.py
"""
import json, glob, os, re, sys, boto3
from botocore.config import Config
from collections import defaultdict

R2_ACCESS = "525c1b593092a9b26c916734a9c344ff"
R2_SECRET = "d35adb29c7ae4f4a89a6c0a8a6679ebee9c769183b6e5bf2b7297202eaf81bec"
R2_ENDPOINT = "https://af76430a7056e37bd99ee03a4468d893.r2.cloudflarestorage.com"
R2_BUCKET = "affine-swe-infinite-private"

print("=" * 60)
print("SWE POOL AUDIT — Complete Coverage Check")
print("=" * 60)

# Step 1: Collect ALL attempted instance_ids from ALL sources
print("\n[1/4] Collecting attempted IDs from all sources...")
attempted = set()
success = set()

# From output files (successful trajectories)
for f in glob.glob("/root/real_distill_v*.jsonl"):
    for line in open(f):
        try:
            iid = json.loads(line)["instance_id"]
            attempted.add(iid)
            success.add(iid)
        except: pass
print(f"  Output files (success): {len(success)}")

# From log files (all attempted, including failures)
for logf in glob.glob("/root/swe_distill_v*.log"):
    with open(logf) as fh:
        for line in fh:
            m = re.match(r'\[(?:R?\d+/\d+)\]\s+(\S+)', line)
            if m: attempted.add(m.group(1))
print(f"  Log files (attempted): {len(attempted)}")

# From canonical file (already synced)
canonical = "/root/canonical_swe_infinite.jsonl"
if os.path.exists(canonical):
    for line in open(canonical):
        try: attempted.add(json.loads(line)["instance_id"])
        except: pass

print(f"  Total unique attempted: {len(attempted)}")

# Step 2: List ENTIRE R2 pool
print("\n[2/4] Listing entire R2 pool...")
s3 = boto3.client("s3", endpoint_url=R2_ENDPOINT, aws_access_key_id=R2_ACCESS,
    aws_secret_access_key=R2_SECRET, config=Config(signature_version="s3v4"), region_name="auto")

pool_keys = []
for page in s3.get_paginator("list_objects_v2").paginate(Bucket=R2_BUCKET, Prefix="", Delimiter="/"):
    for obj in page.get("Contents", []):
        if obj["Key"].endswith(".json"):
            pool_keys.append(obj["Key"])
print(f"  Pool size: {len(pool_keys)} tasks")

# Step 3: Download each task and classify
print("\n[3/4] Downloading and classifying all tasks...")
all_tasks = {}  # instance_id -> task
by_lang = defaultdict(list)
uncovered = defaultdict(list)

for i, key in enumerate(pool_keys):
    try:
        t = json.loads(s3.get_object(Bucket=R2_BUCKET, Key=key)["Body"].read())
        iid = t["instance_id"]
        lang = t.get("repo_language", "unknown").lower()
        all_tasks[iid] = t
        by_lang[lang].append(iid)
        if iid not in attempted:
            uncovered[lang].append(t)
    except Exception as e:
        pass
    if (i+1) % 200 == 0:
        print(f"  {i+1}/{len(pool_keys)}...", flush=True)

# Step 4: Report and generate batch files
print("\n" + "=" * 60)
print("COVERAGE REPORT")
print("=" * 60)
print(f"\nPool total: {len(all_tasks)}")
print(f"Attempted: {len(attempted)}")
print(f"Successful: {len(success)}")
print(f"Uncovered: {sum(len(v) for v in uncovered.values())}")

print(f"\nBy language:")
print(f"{'Language':<12} {'Pool':>6} {'Attempted':>10} {'Uncovered':>10} {'Coverage':>10}")
print("-" * 50)
for lang in sorted(by_lang.keys()):
    total = len(by_lang[lang])
    uncov = len(uncovered.get(lang, []))
    cov = total - uncov
    pct = cov * 100 // total if total > 0 else 0
    print(f"{lang:<12} {total:>6} {cov:>10} {uncov:>10} {pct:>9}%")

# Generate batch files for uncovered tasks
print(f"\n[4/4] Generating batch files for uncovered tasks...")
for lang, tasks in uncovered.items():
    if not tasks:
        continue
    fname = f"/root/swe_batch_{lang}_uncovered.jsonl"
    with open(fname, "w") as f:
        for t in tasks:
            f.write(json.dumps(t) + "\n")
    print(f"  {fname}: {len(tasks)} tasks")

# Also generate a combined "all uncovered" file
all_uncov = []
for tasks in uncovered.values():
    all_uncov.extend(tasks)
if all_uncov:
    with open("/root/swe_batch_all_uncovered.jsonl", "w") as f:
        for t in all_uncov:
            f.write(json.dumps(t) + "\n")
    print(f"  /root/swe_batch_all_uncovered.jsonl: {len(all_uncov)} total uncovered tasks")

print(f"\nAUDIT COMPLETE. {len(all_uncov)} tasks need processing.")
