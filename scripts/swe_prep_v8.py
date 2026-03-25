#!/usr/bin/env python3
"""Quick v8 batch prep: fetch new Go tasks from R2 excluding all batch files."""
import json, glob, os, sys, boto3
from botocore.config import Config

R2_ACCESS = "525c1b593092a9b26c916734a9c344ff"
R2_SECRET = "d35adb29c7ae4f4a89a6c0a8a6679ebee9c769183b6e5bf2b7297202eaf81bec"
R2_ENDPOINT = "https://af76430a7056e37bd99ee03a4468d893.r2.cloudflarestorage.com"
R2_BUCKET = "affine-swe-infinite-private"

s3 = boto3.client("s3", endpoint_url=R2_ENDPOINT, aws_access_key_id=R2_ACCESS,
    aws_secret_access_key=R2_SECRET, config=Config(signature_version="s3v4"), region_name="auto")

# Collect ALL known instance_ids
known = set()
for f in glob.glob("/root/swe_batch_*.jsonl"):
    for line in open(f):
        try: known.add(json.loads(line)["instance_id"])
        except: pass
print(f"Known: {len(known)}", flush=True)

# List and fetch new Go tasks
keys = []
for page in s3.get_paginator("list_objects_v2").paginate(Bucket=R2_BUCKET, Prefix="", Delimiter="/"):
    for obj in page.get("Contents", []):
        if obj["Key"].endswith(".json"): keys.append(obj["Key"])
print(f"Pool: {len(keys)}", flush=True)

new_go = []
for i, key in enumerate(keys):
    try:
        t = json.loads(s3.get_object(Bucket=R2_BUCKET, Key=key)["Body"].read())
        if t.get("repo_language","").lower() == "go" and t["instance_id"] not in known:
            new_go.append(t)
    except: pass
    if (i+1) % 200 == 0: print(f"  {i+1}/{len(keys)}, {len(new_go)} new Go", flush=True)

print(f"New Go: {len(new_go)}", flush=True)
if new_go:
    with open("/root/swe_batch_go_v8.jsonl", "w") as f:
        for t in new_go:
            f.write(json.dumps(t) + "\n")
    print(f"Wrote v8: {len(new_go)} tasks", flush=True)
