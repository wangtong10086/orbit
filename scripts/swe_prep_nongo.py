#!/usr/bin/env python3
"""Prepare non-Go task batches from R2 pool for Claude distillation."""
import json, glob, os, sys, boto3
from botocore.config import Config

R2_ACCESS = "525c1b593092a9b26c916734a9c344ff"
R2_SECRET = "d35adb29c7ae4f4a89a6c0a8a6679ebee9c769183b6e5bf2b7297202eaf81bec"
R2_ENDPOINT = "https://af76430a7056e37bd99ee03a4468d893.r2.cloudflarestorage.com"
R2_BUCKET = "affine-swe-infinite-private"

s3 = boto3.client("s3", endpoint_url=R2_ENDPOINT, aws_access_key_id=R2_ACCESS,
    aws_secret_access_key=R2_SECRET, config=Config(signature_version="s3v4"), region_name="auto")

# Collect ALL known instance_ids from all output files (already attempted)
attempted = set()
for f in glob.glob("/root/real_distill_v*.jsonl"):
    for line in open(f):
        try: attempted.add(json.loads(line)["instance_id"])
        except: pass

# Also from batch files (all tasks we've seen)
batched = set()
for f in glob.glob("/root/swe_batch_*.jsonl"):
    for line in open(f):
        try: batched.add(json.loads(line)["instance_id"])
        except: pass

# Also check logs for attempted instance_ids
import re
for logf in glob.glob("/root/swe_distill_v*.log"):
    with open(logf) as fh:
        for line in fh:
            m = re.match(r'\[(?:R?\d+/\d+)\]\s+(\S+)', line)
            if m: attempted.add(m.group(1))

print(f"Attempted: {len(attempted)}, Batched: {len(batched)}", flush=True)

# List R2 pool
keys = []
for page in s3.get_paginator("list_objects_v2").paginate(Bucket=R2_BUCKET, Prefix="", Delimiter="/"):
    for obj in page.get("Contents", []):
        if obj["Key"].endswith(".json"): keys.append(obj["Key"])
print(f"Pool: {len(keys)}", flush=True)

# Download ALL non-Go tasks (Python, Ruby, Rust, JS)
by_lang = {}
for i, key in enumerate(keys):
    try:
        t = json.loads(s3.get_object(Bucket=R2_BUCKET, Key=key)["Body"].read())
        lang = t.get("repo_language", "").lower()
        iid = t["instance_id"]
        if lang != "go" and lang and iid not in attempted:
            by_lang.setdefault(lang, []).append(t)
    except: pass
    if (i+1) % 200 == 0:
        counts = {k: len(v) for k, v in by_lang.items()}
        print(f"  {i+1}/{len(keys)}, non-Go: {counts}", flush=True)

print(f"\nNew non-Go tasks by language:", flush=True)
for lang, tasks in sorted(by_lang.items(), key=lambda x: -len(x[1])):
    print(f"  {lang}: {len(tasks)}", flush=True)
    fname = f"/root/swe_batch_{lang}_claude.jsonl"
    with open(fname, "w") as f:
        for t in tasks:
            f.write(json.dumps(t) + "\n")
    print(f"  -> wrote {fname}", flush=True)

total = sum(len(v) for v in by_lang.values())
print(f"\nTotal new non-Go tasks: {total}", flush=True)
