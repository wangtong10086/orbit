#!/usr/bin/env python3
"""Fetch new Go tasks from R2 pool, excluding all previously batched tasks."""
import json, glob, urllib.request

# Collect all known instance_ids from batch files
known_ids = set()
for f in glob.glob("/root/swe_batch_*.jsonl"):
    for line in open(f):
        try:
            known_ids.add(json.loads(line)["instance_id"])
        except:
            pass
print(f"Known batch IDs: {len(known_ids)}")

# Try R2 index
try:
    resp = urllib.request.urlopen(
        "https://pub-7882418a56434a479bf9a7febd660b36.r2.dev/bugs/index.json", timeout=30
    )
    tasks = json.loads(resp.read())
    print(f"R2 index: {len(tasks)} total tasks")

    # Filter: Go only, not already batched
    new_go = [t for t in tasks if t.get("repo_language", "").lower() == "go" and t["instance_id"] not in known_ids]
    print(f"New Go tasks: {len(new_go)}")

    if new_go:
        mid = len(new_go) // 2
        with open("/root/swe_batch_go_v7a.jsonl", "w") as f:
            for t in new_go[:mid]:
                f.write(json.dumps(t) + "\n")
        with open("/root/swe_batch_go_v7b.jsonl", "w") as f:
            for t in new_go[mid:]:
                f.write(json.dumps(t) + "\n")
        print(f"Wrote v7a: {mid}, v7b: {len(new_go) - mid}")
    else:
        print("No new Go tasks")
except Exception as e:
    print(f"R2 index failed: {e}")
    # Fallback: try listing expansion bucket
    try:
        resp = urllib.request.urlopen(
            "https://pub-7882418a56434a479bf9a7febd660b36.r2.dev/expansion/index.json", timeout=30
        )
        tasks = json.loads(resp.read())
        print(f"Expansion index: {len(tasks)} tasks")
    except Exception as e2:
        print(f"Expansion index also failed: {e2}")
        print("Need to use affine-swe-infinite pipeline to fetch tasks from R2")
