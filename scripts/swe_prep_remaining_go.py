#!/usr/bin/env python3
"""Prepare remaining Go tasks that haven't been batched yet."""
import json, glob, os, sys, boto3
from botocore.config import Config

R2_ACCESS = "525c1b593092a9b26c916734a9c344ff"
R2_SECRET = "d35adb29c7ae4f4a89a6c0a8a6679ebee9c769183b6e5bf2b7297202eaf81bec"
R2_ENDPOINT = "https://af76430a7056e37bd99ee03a4468d893.r2.cloudflarestorage.com"
R2_BUCKET = "affine-swe-infinite-private"

s3 = boto3.client("s3", endpoint_url=R2_ENDPOINT, aws_access_key_id=R2_ACCESS,
    aws_secret_access_key=R2_SECRET, config=Config(signature_version="s3v4"), region_name="auto")

# Collect ALL known Go instance_ids from batch files
known_go = set()
for f in glob.glob("/root/swe_batch_go_*.jsonl"):
    for line in open(f):
        try:
            t = json.loads(line)
            if t.get("repo_language", "").lower() == "go":
                known_go.add(t["instance_id"])
        except: pass
# Also from v4 batch (swe_batch_go_200.jsonl)
for f in ["/root/swe_batch_go_200.jsonl"]:
    if os.path.exists(f):
        for line in open(f):
            try: known_go.add(json.loads(line)["instance_id"])
            except: pass

print(f"Known Go IDs: {len(known_go)}", flush=True)

# List R2 and find new Go tasks
keys = []
for page in s3.get_paginator("list_objects_v2").paginate(Bucket=R2_BUCKET, Prefix="", Delimiter="/"):
    for obj in page.get("Contents", []):
        if obj["Key"].endswith(".json"): keys.append(obj["Key"])
print(f"Pool: {len(keys)}", flush=True)

new_go = []
for i, key in enumerate(keys):
    try:
        t = json.loads(s3.get_object(Bucket=R2_BUCKET, Key=key)["Body"].read())
        if t.get("repo_language", "").lower() == "go" and t["instance_id"] not in known_go:
            new_go.append(t)
    except: pass
    if (i+1) % 200 == 0:
        print(f"  {i+1}/{len(keys)}, {len(new_go)} new Go", flush=True)

print(f"\nNew Go tasks: {len(new_go)}", flush=True)
if new_go:
    # Split into 2 for concurrent
    mid = len(new_go) // 2
    with open("/root/swe_batch_go_v9a.jsonl", "w") as f:
        for t in new_go[:mid]:
            f.write(json.dumps(t) + "\n")
    with open("/root/swe_batch_go_v9b.jsonl", "w") as f:
        for t in new_go[mid:]:
            f.write(json.dumps(t) + "\n")
    print(f"Wrote v9a: {mid}, v9b: {len(new_go)-mid}", flush=True)
