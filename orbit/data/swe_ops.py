"""SWE-Infinite collection operations — monitor, sync, manage batches.

Provides SSH-based management of SWE collection running on remote hosts.
Handles collector status, manifest-aware syncing, and canonical updates.
"""

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Remote machine config
DEFAULT_SWE_SSH = "wrk-2g5l02247zvp@ssh.deployments.targon.com"
CANONICAL_FILE = "data/canonical/swe_infinite.jsonl"
SYNTH_CONFIG = "synth_config.json"
DEFAULT_REMOTE_OUTPUT_DIR = "/root/orbit-swe-collect"


def _canonical_file(canonical_dir: str | None = None) -> Path:
    if canonical_dir:
        return Path(canonical_dir) / Path(CANONICAL_FILE).name
    return Path(CANONICAL_FILE)


def _entry_key(entry: dict) -> str:
    return str(entry.get("sample_id") or entry.get("instance_id") or "")


@dataclass(frozen=True)
class SweTarget:
    host: str
    ssh_args: tuple[str, ...] = ()
    scp_args: tuple[str, ...] = ()


def _machines_file() -> Path:
    return Path(os.getenv("ORBIT_MACHINES_FILE", "machines.json"))


def _resolve_target(machine: str | None = None) -> SweTarget:
    env_host = os.getenv("SWE_DISTILL_SSH", "").strip()
    env_key = os.getenv("SWE_DISTILL_SSH_KEY", "").strip()
    env_port = os.getenv("SWE_DISTILL_SSH_PORT", "").strip()

    if machine:
        machines_path = _machines_file()
        if not machines_path.exists():
            raise FileNotFoundError(f"machines.json not found: {machines_path}")
        with machines_path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        machines = data.get("machines", [])
        selected = None
        if machine.isdigit():
            idx = int(machine)
            if 0 <= idx < len(machines):
                selected = machines[idx]
        else:
            selected = next((item for item in machines if item.get("name") == machine), None)
        if selected is None:
            raise KeyError(f"Unknown SWE machine selector: {machine}")
        host = f"{selected.get('user', 'root')}@{selected['host']}"
        ssh_args: list[str] = []
        scp_args: list[str] = []
        port = selected.get("port")
        if port:
            ssh_args.extend(["-p", str(port)])
            scp_args.extend(["-P", str(port)])
        key = selected.get("key")
        if key:
            ssh_args.extend(["-i", key])
            scp_args.extend(["-i", key])
        return SweTarget(host=host, ssh_args=tuple(ssh_args), scp_args=tuple(scp_args))

    ssh_args = []
    scp_args = []
    if env_port:
        ssh_args.extend(["-p", env_port])
        scp_args.extend(["-P", env_port])
    if env_key:
        ssh_args.extend(["-i", env_key])
        scp_args.extend(["-i", env_key])
    return SweTarget(host=env_host or DEFAULT_SWE_SSH, ssh_args=tuple(ssh_args), scp_args=tuple(scp_args))


def _ssh_run(cmd: str, timeout: int = 30, machine: str | None = None) -> tuple[str, int]:
    """Execute command on remote distillation machine via SSH."""
    target = _resolve_target(machine)
    try:
        r = subprocess.run(
            ["ssh", *target.ssh_args, "-o", "ConnectTimeout=10", "-o", "BatchMode=yes", target.host, cmd],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"ssh timed out after {timeout} seconds", 124
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


def _remote_blocker(action: str, output: str, returncode: int) -> Optional[str]:
    """Classify SSH/connectivity failures as explicit infrastructure blockers."""
    if returncode in (0, 1) and not output.strip():
        return None
    if returncode == 0:
        return None
    return f"{action} failed: {output.strip()}"


def _scp_from(remote_path: str, local_path: str, timeout: int = 60, machine: str | None = None) -> bool:
    """Copy file from remote to local via SCP."""
    target = _resolve_target(machine)
    r = subprocess.run(
        ["scp", *target.scp_args, "-o", "ConnectTimeout=10", f"{target.host}:{remote_path}", local_path],
        capture_output=True, text=True, timeout=timeout,
    )
    return r.returncode == 0


def distill_status(machine: str | None = None) -> dict:
    """Check collection process status on remote machine.

    Returns dict with keys: running (bool), processes (list),
    output_files (list of {name, count}), containers (int), runs (list).
    """
    result = {
        "running": False,
        "processes": [],
        "output_files": [],
        "containers": 0,
        "runs": [],
        "infra_error": None,
        "probe_warning": None,
    }

    # Check running processes
    out, rc = _ssh_run("ps aux | grep -E 'orbit data swe-collect|swe-collect' | grep -v grep", machine=machine)
    blocker = _remote_blocker("process probe", out, rc)
    if blocker:
        result["infra_error"] = blocker
        return result
    if out:
        result["running"] = True
        for line in out.strip().split("\n"):
            parts = line.split()
            pid = parts[1] if len(parts) > 1 else "?"
            # Extract --output and --task-file from command
            cmd = " ".join(parts[10:]) if len(parts) > 10 else ""
            result["processes"].append({"pid": pid, "cmd": cmd})

    # Check exported canonical files from the new collector layout.
    out, rc = _ssh_run(
        f"find {DEFAULT_REMOTE_OUTPUT_DIR} -path '*/canonical/*.jsonl' -type f "
        "-exec sh -lc 'printf \"%s %s\\n\" \"$(basename \"$1\")\" \"$(wc -l < \"$1\")\"' _ {{}} \\; 2>/dev/null",
        machine=machine,
    )
    blocker = _remote_blocker("output file probe", out, rc)
    if blocker:
        result["infra_error"] = blocker
        return result
    if out:
        for line in out.strip().split("\n"):
            parts = line.split()
            if len(parts) == 2:
                try:
                    result["output_files"].append({"name": parts[0], "count": int(parts[1])})
                except ValueError:
                    pass

    # Check running containers
    out, rc = _ssh_run("docker ps --format '{{.Names}}' | grep orbit-swe | wc -l", machine=machine)
    blocker = _remote_blocker("container probe", out, rc)
    if blocker:
        if "timed out" in blocker.lower():
            result["probe_warning"] = blocker
            return result
        result["infra_error"] = blocker
        return result
    if out:
        try:
            result["containers"] = int(out.strip())
        except ValueError:
            result["probe_warning"] = f"container probe returned non-numeric output: {out.strip()}"
            return result

    out, rc = _ssh_run(
        f"find {DEFAULT_REMOTE_OUTPUT_DIR} -path '*/manifests/run.json' -type f -print 2>/dev/null",
        machine=machine,
    )
    blocker = _remote_blocker("run manifest probe", out, rc)
    if blocker:
        result["infra_error"] = blocker
        return result
    if out:
        result["runs"] = [line.strip() for line in out.splitlines() if line.strip()]

    return result


def distill_log(lines: int = 30, batch: str = "latest", machine: str | None = None) -> str:
    """Get recent collector log output.

    Args:
        lines: Number of log lines to return
        batch: Attempt-id stem or `latest`
    """
    if batch == "latest":
        cmd = (
            f"latest=$(find {DEFAULT_REMOTE_OUTPUT_DIR} -path '*/logs/*.log' -type f 2>/dev/null | sort | tail -1); "
            f"[ -n \"$latest\" ] && tail -{lines} \"$latest\""
        )
    else:
        cmd = f"tail -{lines} {DEFAULT_REMOTE_OUTPUT_DIR}/logs/{batch}.log 2>/dev/null"
    out, _ = _ssh_run(cmd, machine=machine)
    return out or "(no log output)"


def count_local_canonical() -> dict:
    """Count entries in local canonical SWE file by language."""
    counts = {"total": 0, "by_language": {}}
    canon = _canonical_file()
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


def sync_new_trajectories(
    dry_run: bool = False,
    machine: str | None = None,
    canonical_dir: str | None = None,
    staging_path: str | None = None,
    raw_output_dir: str | None = None,
    remote_dir: str | None = None,
) -> dict:
    """Sync new trajectories from remote to canonical.

    Downloads remote output files, deduplicates against canonical,
    validates format, and appends new entries.

    Returns dict with keys: new_count, skipped_dup, skipped_invalid, total.
    """
    result = {"new_count": 0, "skipped_dup": 0, "skipped_invalid": 0, "total": 0, "blocked_reason": None}

    # Load existing canonical IDs
    existing_ids = set()
    canon = _canonical_file(canonical_dir)
    canon.parent.mkdir(parents=True, exist_ok=True)
    if canon.exists():
        with open(canon) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    existing_ids.add(_entry_key(entry))
                except json.JSONDecodeError:
                    pass
    result["total"] = len(existing_ids)

    remote_root = remote_dir or DEFAULT_REMOTE_OUTPUT_DIR

    # Find remote output files
    status = distill_status(machine=machine) if machine is not None else distill_status()
    if status.get("infra_error"):
        result["blocked_reason"] = status["infra_error"]
        return result

    out, rc = _ssh_run(
        f"find {remote_root} -path '*/canonical/*.jsonl' -type f -print 2>/dev/null",
        machine=machine,
    )
    blocker = _remote_blocker("sync file probe", out, rc)
    if blocker:
        result["blocked_reason"] = blocker
        return result
    remote_files = [line.strip() for line in out.splitlines() if line.strip()]

    if not remote_files:
        return result

    # Download and process each file
    tmp_dir = Path("/tmp/swe-sync")
    tmp_dir.mkdir(exist_ok=True)

    new_entries = []
    raw_files: list[str] = []
    for remote_path in remote_files:
        fname = Path(remote_path).name
        local_tmp = tmp_dir / fname
        if not _scp_from(remote_path, str(local_tmp), machine=machine):
            continue
        if raw_output_dir:
            raw_dir = Path(raw_output_dir)
            raw_dir.mkdir(parents=True, exist_ok=True)
            raw_dest = raw_dir / fname
            raw_dest.write_bytes(local_tmp.read_bytes())
            raw_files.append(str(raw_dest))

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

                entry_key = _entry_key(entry)
                if entry_key in existing_ids:
                    result["skipped_dup"] += 1
                    continue

                # Validate required fields
                issues = _validate_swe_entry(entry)
                if issues:
                    result["skipped_invalid"] += 1
                    continue

                existing_ids.add(entry_key)
                new_entries.append(entry)

    if staging_path and new_entries:
        staging_file = Path(staging_path)
        staging_file.parent.mkdir(parents=True, exist_ok=True)
        with staging_file.open("w", encoding="utf-8") as handle:
            for entry in new_entries:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    if new_entries and not dry_run:
        with open(canon, "a") as f:
            for entry in new_entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    result["new_count"] = len(new_entries)
    result["total"] = len(existing_ids)
    result["raw_files"] = raw_files
    result["staging_path"] = staging_path or ""
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

    if msgs and msgs[-1].get("role") not in {"assistant", "tool"}:
        issues.append("last message not assistant/tool")

    # Check for think tags
    for m in msgs:
        if m.get("role") == "assistant" and "<think>" in m.get("content", ""):
            issues.append("contains think tags")
            break

    for m in msgs:
        if m.get("role") == "tool" and not m.get("tool_call_id", ""):
            issues.append("tool message missing tool_call_id")
            break

    return issues
