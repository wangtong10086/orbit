#!/usr/bin/env python3
"""Fetch new Go tasks from R2 private pool for v7 batch."""
import json, os, sys

# R2 credentials from .env
R2_ACCESS = os.environ.get("R2_ACCESS_KEY_ID", "525c1b593092a9b26c916734a9c344ff")
R2_SECRET = os.environ.get("R2_SECRET_ACCESS_KEY", "d35adb29c7ae4f4a89a6c0a8a6679ebee9c769183b6e5bf2b7297202eaf81bec")
R2_ENDPOINT = os.environ.get("R2_ENDPOINT_URL", "https://af76430a7056e37bd99ee03a4468d893.r2.cloudflarestorage.com")
R2_BUCKET = os.environ.get("R2_BUCKET", "affine-swe-infinite-private")

import boto3
from botocore.config import Config

s3 = boto3.client(
    "s3",
    endpoint_url=R2_ENDPOINT,
    aws_access_key_id=R2_ACCESS,
    aws_secret_access_key=R2_SECRET,
    config=Config(signature_version="s3v4"),
    region_name="auto",
)

# List all top-level JSON files (unreleased tasks)
print("Listing R2 private bucket...")
keys = []
paginator = s3.get_paginator("list_objects_v2")
for page in paginator.paginate(Bucket=R2_BUCKET, Prefix="", Delimiter="/"):
    for obj in page.get("Contents", []):
        key = obj["Key"]
        if key.endswith(".json"):
            keys.append(key)
print(f"Total tasks in pool: {len(keys)}")

# Load known instance_ids from batch files on m2
import glob
known_ids = set()
for f in glob.glob("/root/swe_batch_*.jsonl"):
    for line in open(f):
        try:
            known_ids.add(json.loads(line)["instance_id"])
        except:
            pass
print(f"Known batch IDs: {len(known_ids)}")

# Download and filter new Go tasks
new_go = []
checked = 0
for key in keys:
    try:
        resp = s3.get_object(Bucket=R2_BUCKET, Key=key)
        task = json.loads(resp["Body"].read())
        iid = task.get("instance_id", "")
        lang = task.get("repo_language", "").lower()
        checked += 1
        if checked % 100 == 0:
            print(f"  Checked {checked}/{len(keys)}, found {len(new_go)} new Go tasks...")
        if lang == "go" and iid not in known_ids:
            new_go.append(task)
    except Exception as e:
        pass

print(f"\nNew Go tasks: {len(new_go)}")

if new_go:
    mid = len(new_go) // 2
    with open("/root/swe_batch_go_v7a.jsonl", "w") as f:
        for t in new_go[:mid]:
            f.write(json.dumps(t) + "\n")
    with open("/root/swe_batch_go_v7b.jsonl", "w") as f:
        for t in new_go[mid:]:
            f.write(json.dumps(t) + "\n")
    print(f"Wrote v7a: {mid} tasks, v7b: {len(new_go) - mid} tasks")
else:
    print("No new Go tasks available")
