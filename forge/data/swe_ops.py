"""SWE-Infinite distillation operations — monitor, sync, manage batches.

Provides SSH-based management of SWE trajectory distillation running on
remote GPU machines. Handles progress monitoring, trajectory syncing to
canonical, and batch management.
"""

import json
import subprocess
import os
from pathlib import Path
from typing import Optional

# Remote machine config
M2_SSH = os.getenv(
    "SWE_DISTILL_SSH",
    "wrk-2g5l02247zvp@ssh.deployments.targon.com",
)
CANONICAL_FILE = "data/canonical/swe_infinite.jsonl"
SYNTH_CONFIG = "synth_config.json"


def _ssh_run(cmd: str, timeout: int = 30) -> tuple[str, int]:
    """Execute command on remote distillation machine via SSH."""
    r = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=10", "-o", "BatchMode=yes", M2_SSH, cmd],
        capture_output=True, text=True, timeout=timeout,
    )
    # Filter out Targon's "Connecting to container..." preamble from both streams
    def _filter(text: str) -> str:
        return "\n".join(
            line for line in (text or "").splitlines()
            if not line.startswith("Connecting to container")
        )

    output = _filter(r.stdout)
    stderr = _filter(r.stderr)
    if stderr:
        output = f"{output}\n{stderr}" if output else stderr
    return output.strip(), r.returncode


def _scp_from(remote_path: str, local_path: str, timeout: int = 60) -> bool:
    """Copy file from remote to local via SCP."""
    r = subprocess.run(
        ["scp", "-o", "ConnectTimeout=10", f"{M2_SSH}:{remote_path}", local_path],
        capture_output=True, text=True, timeout=timeout,
    )
    return r.returncode == 0


def distill_status() -> dict:
    """Check distillation process status on remote machine.

    Returns dict with keys: running (bool), processes (list),
    output_files (list of {name, count}), containers (int).
    """
    result = {"running": False, "processes": [], "output_files": [], "containers": 0}

    # Check running processes
    out, rc = _ssh_run("ps aux | grep swe_distill | grep -v grep")
    if out:
        result["running"] = True
        for line in out.strip().split("\n"):
            parts = line.split()
            pid = parts[1] if len(parts) > 1 else "?"
            # Extract --output and --task-file from command
            cmd = " ".join(parts[10:]) if len(parts) > 10 else ""
            result["processes"].append({"pid": pid, "cmd": cmd})

    # Check all output files (v3, v4, v5, etc.)
    out, rc = _ssh_run(
        "for f in /root/real_distill_v*.jsonl; do "
        "[ -f \"$f\" ] && echo \"$(basename $f) $(wc -l < $f)\"; "
        "done 2>/dev/null"
    )
    if out:
        for line in out.strip().split("\n"):
            parts = line.split()
            if len(parts) == 2:
                try:
                    result["output_files"].append({"name": parts[0], "count": int(parts[1])})
                except ValueError:
                    pass

    # Check running containers
    out, rc = _ssh_run("docker ps --format '{{.Names}}' | grep swe-distill | wc -l")
    if out:
        result["containers"] = int(out.strip())

    return result


def distill_log(lines: int = 30, batch: str = "v4") -> str:
    """Get recent log output from distillation.

    Args:
        lines: Number of log lines to return
        batch: Which batch log to read (v4, v4_ruby_rust, etc.)
    """
    suffix = f"_{batch}" if batch != "v4" else "_v4"
    out, _ = _ssh_run(f"tail -{lines} /root/swe_distill{suffix}.log 2>/dev/null")
    return out or "(no log output)"


def count_local_canonical() -> dict:
    """Count entries in local canonical SWE file by language."""
    counts = {"total": 0, "by_language": {}}
    canon = Path(CANONICAL_FILE)
    if not canon.exists():
        return counts

    with open(canon) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                lang = entry.get("language", "unknown")
                counts["by_language"][lang] = counts["by_language"].get(lang, 0) + 1
                counts["total"] += 1
            except json.JSONDecodeError:
                pass

    return counts


def sync_new_trajectories(dry_run: bool = False) -> dict:
    """Sync new trajectories from remote to canonical.

    Downloads remote output files, deduplicates against canonical,
    validates format, and appends new entries.

    Returns dict with keys: new_count, skipped_dup, skipped_invalid, total.
    """
    result = {"new_count": 0, "skipped_dup": 0, "skipped_invalid": 0, "total": 0}

    # Load existing canonical IDs
    existing_ids = set()
    canon = Path(CANONICAL_FILE)
    if canon.exists():
        with open(canon) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    existing_ids.add(entry.get("instance_id", ""))
                except json.JSONDecodeError:
                    pass
    result["total"] = len(existing_ids)

    # Find remote output files
    status = distill_status()
    remote_files = []
    for of in status["output_files"]:
        if of["count"] > 0:
            remote_files.append(of["name"])

    if not remote_files:
        return result

    # Download and process each file
    tmp_dir = Path("/tmp/swe-sync")
    tmp_dir.mkdir(exist_ok=True)

    new_entries = []
    for fname in remote_files:
        local_tmp = tmp_dir / fname
        if not _scp_from(f"/root/{fname}", str(local_tmp)):
            continue

        with open(local_tmp) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    result["skipped_invalid"] += 1
                    continue

                iid = entry.get("instance_id", "")
                if iid in existing_ids:
                    result["skipped_dup"] += 1
                    continue

                # Validate required fields
                issues = _validate_swe_entry(entry)
                if issues:
                    result["skipped_invalid"] += 1
                    continue

                existing_ids.add(iid)
                new_entries.append(entry)

    if new_entries and not dry_run:
        with open(canon, "a") as f:
            for entry in new_entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    result["new_count"] = len(new_entries)
    result["total"] = len(existing_ids)
    return result


def _validate_swe_entry(entry: dict) -> list[str]:
    """Validate a SWE-Infinite trajectory entry."""
    issues = []

    if entry.get("env") != "SWE-INFINITE":
        issues.append(f"wrong env: {entry.get('env')}")

    score = entry.get("score", 0)
    if score < 1.0:
        issues.append(f"score {score} < 1.0")

    msgs = entry.get("messages", [])
    if len(msgs) < 4:
        issues.append(f"too few messages: {len(msgs)}")

    if msgs and msgs[-1].get("role") != "assistant":
        issues.append("last message not assistant")

    # Check for think tags
    for m in msgs:
        if m.get("role") == "assistant" and "<think>" in m.get("content", ""):
            issues.append("contains think tags")
            break

    return issues
