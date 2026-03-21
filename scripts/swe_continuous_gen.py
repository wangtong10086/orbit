#!/usr/bin/env python3
"""
SWE-Infinite Continuous Trajectory Generator

Monitors the private R2 pool for new tasks and generates synthetic
trajectories continuously. Tracks processed tasks to avoid duplicates.

Usage:
    python3 scripts/swe_continuous_gen.py --output data/swe_infinite_synth_v2.jsonl
"""

import argparse
import datetime
import hashlib
import hmac
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.error import HTTPError

# Import synth gen logic from existing script
sys.path.insert(0, str(Path(__file__).parent))
from swe_synth_gen import (
    SYSTEM_PROMPT, INSTANCE_TEMPLATE, SYNTH_SYSTEM,
    call_llm, generate_trajectory, _load_dotenv,
    ACTION_RE,
)


# ---------------------------------------------------------------------------
# R2 Client (pure Python, no boto3)
# ---------------------------------------------------------------------------

class R2Client:
    def __init__(self):
        self.endpoint = os.environ["R2_ENDPOINT_URL"]
        self.bucket = os.environ["R2_BUCKET"]
        self.ak = os.environ["R2_ACCESS_KEY_ID"]
        self.sk = os.environ["R2_SECRET_ACCESS_KEY"]
        self.host = self.endpoint.replace("https://", "").rstrip("/")

    def _sign(self, key, msg):
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    def _get_signing_key(self, ds):
        return self._sign(
            self._sign(
                self._sign(
                    self._sign(("AWS4" + self.sk).encode(), ds),
                    "auto"),
                "s3"),
            "aws4_request")

    def _signed_request(self, method, uri, qs=""):
        now = datetime.datetime.now(datetime.UTC)
        ds = now.strftime("%Y%m%d")
        amz = now.strftime("%Y%m%dT%H%M%SZ")
        ph = hashlib.sha256(b"").hexdigest()
        ch = f"host:{self.host}\nx-amz-content-sha256:{ph}\nx-amz-date:{amz}\n"
        sh = "host;x-amz-content-sha256;x-amz-date"
        cr = f"{method}\n{uri}\n{qs}\n{ch}\n{sh}\n{ph}"
        cs = f"{ds}/auto/s3/aws4_request"
        sts = f"AWS4-HMAC-SHA256\n{amz}\n{cs}\n{hashlib.sha256(cr.encode()).hexdigest()}"
        sig = hmac.new(self._get_signing_key(ds), sts.encode(), hashlib.sha256).hexdigest()
        auth = f"AWS4-HMAC-SHA256 Credential={self.ak}/{cs}, SignedHeaders={sh}, Signature={sig}"
        url = f"{self.endpoint}{uri}" + (f"?{qs}" if qs else "")
        return urllib.request.Request(url, headers={
            "Host": self.host, "x-amz-date": amz,
            "x-amz-content-sha256": ph, "Authorization": auth,
        })

    def list_tasks(self) -> list[str]:
        """List all task instance_ids in the private pool."""
        all_keys = []
        token = None
        while True:
            params = {"list-type": "2", "max-keys": "1000"}
            if token:
                params["continuation-token"] = token
            qs = "&".join(
                f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
                for k, v in sorted(params.items())
            )
            req = self._signed_request("GET", f"/{self.bucket}", qs)
            with urllib.request.urlopen(req, timeout=30) as resp:
                root = ET.fromstring(resp.read().decode())

            keys = [c.text for c in root.iter() if c.tag.endswith("Key") and c.text]
            all_keys.extend(keys)

            truncated = any(c.text == "true" for c in root.iter() if c.tag.endswith("IsTruncated"))
            next_tokens = [c.text for c in root.iter() if c.tag.endswith("NextContinuationToken") and c.text]
            if truncated and next_tokens:
                token = next_tokens[0]
            else:
                break

        return [k.replace(".json", "") for k in all_keys if k.endswith(".json")]

    def get_task(self, instance_id: str) -> dict:
        """Fetch a single task by instance_id."""
        key = f"{instance_id}.json"
        uri = f"/{self.bucket}/{urllib.parse.quote(key, safe='/')}"
        req = self._signed_request("GET", uri)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())


def load_processed(output_path: str) -> set[str]:
    """Load already-processed instance_ids."""
    processed = set()
    if os.path.exists(output_path):
        with open(output_path) as f:
            for line in f:
                try:
                    e = json.loads(line.strip())
                    processed.add(e.get("instance_id", ""))
                except (json.JSONDecodeError, KeyError):
                    pass
    # Also load from older output files
    for old in ["data/swe_infinite_synth_deduped.jsonl",
                "data/staging/swe_infinite_v1.jsonl",
                "data/staging/swe_infinite_merged.jsonl"]:
        if os.path.exists(old):
            try:
                with open(old) as f:
                    for line in f:
                        try:
                            processed.add(json.loads(line.strip()).get("instance_id", ""))
                        except:
                            pass
            except:
                pass
    return processed


def main():
    _load_dotenv()
    parser = argparse.ArgumentParser(description="SWE-Infinite continuous trajectory generator")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--api-base", default=os.getenv("OPENAI_BASE_URL", ""))
    parser.add_argument("--api-key", default=os.getenv("OPENAI_API_KEY", ""))
    parser.add_argument("--output", default="data/swe_infinite_synth_v2.jsonl")
    parser.add_argument("--max-patch-size", type=int, default=5000)
    parser.add_argument("--batch-size", type=int, default=0,
                        help="Process at most N new tasks (0=all)")
    args = parser.parse_args()

    if not args.api_key:
        print("ERROR: need API key")
        sys.exit(1)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    r2 = R2Client()
    processed = load_processed(args.output)
    print(f"Already processed: {len(processed)}")

    # List all tasks in private pool
    print("Listing private pool...")
    pool = r2.list_tasks()
    print(f"Private pool: {len(pool)} tasks")

    new_tasks = [t for t in pool if t not in processed]
    print(f"New tasks: {len(new_tasks)}")

    if args.batch_size > 0:
        new_tasks = new_tasks[:args.batch_size]
        print(f"Processing batch of {len(new_tasks)}")

    stats = {"success": 0, "fail": 0, "skip_large": 0, "api_error": 0}

    for i, tid in enumerate(new_tasks):
        print(f"\n[{i+1}/{len(new_tasks)}] {tid}")

        try:
            task = r2.get_task(tid)
        except Exception as e:
            print(f"  R2 fetch error: {e}")
            stats["api_error"] += 1
            continue

        if len(task.get("patch", "")) > args.max_patch_size:
            print(f"  Skip (patch {len(task['patch'])}c > {args.max_patch_size})")
            stats["skip_large"] += 1
            continue

        result = generate_trajectory(task, args.model, args.api_base, args.api_key)
        if result is None:
            print(f"  FAIL")
            stats["fail"] += 1
            continue

        asst = [m for m in result["messages"] if m["role"] == "assistant"]
        with open(args.output, "a") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
        print(f"  OK ({len(asst)} turns, {task.get('repo_language', '?')})")
        stats["success"] += 1

    total = sum(stats.values())
    effective = total - stats["skip_large"]
    print(f"\n{'='*50}")
    print(f"COMPLETE: {stats['success']} OK, {stats['fail']} fail, "
          f"{stats['skip_large']} skip, {stats['api_error']} api_err")
    if effective > 0:
        print(f"Success rate: {stats['success']}/{effective} = "
              f"{stats['success']*100//effective}%")


if __name__ == "__main__":
    main()
