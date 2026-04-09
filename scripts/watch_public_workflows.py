#!/usr/bin/env python3
"""Poll GitHub Actions runs for a public repo commit until required workflows succeed."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time
import urllib.parse
import urllib.request


def _api_json(url: str, token: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "orbit-public-workflow-watch",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def _summarize_runs(runs: list[dict], workflows: list[str]) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for workflow in workflows:
        matches = [run for run in runs if run.get("name") == workflow]
        if not matches:
            continue
        latest[workflow] = max(matches, key=lambda run: run.get("id", 0))
    return latest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--sha", required=True, help="Public repo commit SHA to watch")
    parser.add_argument("--workflow", action="append", required=True, help="Required workflow name; repeatable")
    parser.add_argument("--event", default="workflow_dispatch", help="GitHub Actions event to filter on")
    parser.add_argument("--timeout-seconds", type=int, default=7200)
    parser.add_argument("--poll-seconds", type=int, default=15)
    parser.add_argument("--result-json", default="", help="Write final workflow status summary to this path")
    args = parser.parse_args()

    token = os.environ.get("GH_TOKEN", "").strip() or os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise SystemExit("GH_TOKEN or GITHUB_TOKEN is required")

    deadline = time.time() + args.timeout_seconds
    owner, name = args.repo.split("/", 1)
    query = urllib.parse.urlencode({"head_sha": args.sha, "event": args.event, "per_page": 100})
    url = f"https://api.github.com/repos/{owner}/{name}/actions/runs?{query}"
    required = list(dict.fromkeys(args.workflow))

    while time.time() < deadline:
        payload = _api_json(url, token)
        runs = payload.get("workflow_runs", [])
        latest = _summarize_runs(runs, required)
        missing = [workflow for workflow in required if workflow not in latest]
        failures = [
            run
            for run in latest.values()
            if run.get("status") == "completed" and run.get("conclusion") != "success"
        ]
        pending = [run for run in latest.values() if run.get("status") != "completed"]
        result = {
            "repo": args.repo,
            "sha": args.sha,
            "event": args.event,
            "required_workflows": required,
            "missing_workflows": missing,
            "runs": {
                workflow: {
                    "id": run.get("id"),
                    "status": run.get("status"),
                    "conclusion": run.get("conclusion"),
                    "url": run.get("html_url"),
                }
                for workflow, run in latest.items()
            },
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        if failures:
            if args.result_json:
                Path(args.result_json).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            raise SystemExit(1)
        if not missing and not pending:
            if args.result_json:
                Path(args.result_json).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return 0
        time.sleep(args.poll_seconds)

    raise SystemExit("timed out waiting for required public workflows")
