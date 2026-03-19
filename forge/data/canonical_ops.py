"""Canonical data operations — validate, append, sync to HF.

Single entry point for all canonical data mutations. Ensures format
consistency, deduplication, and HF sync on every change.
"""

import hashlib
import json
import os
from typing import Optional


CANONICAL_DIR = "data/canonical"
HF_REPO = "monokoco/affine-sft-data"

# Required message schema: every message must have exactly these fields
REQUIRED_MSG_FIELDS = {"role", "content"}

# Valid roles per environment
VALID_ROLES = {
    "GAME": {"system", "user", "assistant"},
    "NAVWORLD": {"system", "user", "assistant", "tool"},
    "SWE-SYNTH": {"system", "user", "assistant"},
    "LIVEWEB": {"system", "user", "assistant"},
    "LGC-v2": {"user", "assistant"},
    "PRINT": {"user", "assistant"},
}


def _entry_fingerprint(entry: dict) -> str:
    """MD5 of all message contents for deduplication."""
    parts = []
    for msg in entry.get("messages", []):
        parts.append(f"{msg.get('role', '')}:{msg.get('content', '')}")
    return hashlib.md5("|".join(parts).encode()).hexdigest()


def validate_entry(entry: dict, expected_env: str) -> list[str]:
    """Validate a single entry. Returns list of issues (empty = valid)."""
    issues = []

    # Top-level fields
    if "messages" not in entry:
        issues.append("missing 'messages' field")
        return issues
    if entry.get("env") != expected_env:
        issues.append(f"env='{entry.get('env')}' expected '{expected_env}'")
    if "score" not in entry:
        issues.append("missing 'score' field")

    msgs = entry["messages"]
    if len(msgs) < 2:
        issues.append(f"only {len(msgs)} messages (need ≥2)")

    # Message schema
    valid_roles = VALID_ROLES.get(expected_env, {"system", "user", "assistant"})
    for i, msg in enumerate(msgs):
        keys = set(msg.keys())
        if keys != REQUIRED_MSG_FIELDS:
            extra = keys - REQUIRED_MSG_FIELDS
            missing = REQUIRED_MSG_FIELDS - keys
            if extra:
                issues.append(f"msg[{i}]: extra fields {extra}")
            if missing:
                issues.append(f"msg[{i}]: missing fields {missing}")

        if msg.get("content") is None:
            issues.append(f"msg[{i}]: content is None")

        role = msg.get("role", "")
        if role not in valid_roles:
            issues.append(f"msg[{i}]: role='{role}' not in {valid_roles}")

    # Last message must be assistant
    if msgs and msgs[-1].get("role") != "assistant":
        issues.append(f"last msg role='{msgs[-1].get('role')}' (must be assistant)")

    return issues


def validate_batch(entries: list[dict], expected_env: str) -> dict:
    """Validate a batch of entries. Returns summary dict."""
    total = len(entries)
    valid = 0
    invalid = 0
    all_issues = []

    for i, entry in enumerate(entries):
        issues = validate_entry(entry, expected_env)
        if issues:
            invalid += 1
            all_issues.append((i, issues))
        else:
            valid += 1

    return {
        "total": total,
        "valid": valid,
        "invalid": invalid,
        "issues": all_issues,
    }


def load_canonical(env: str) -> list[dict]:
    """Load all entries from a canonical file."""
    fname = _env_to_filename(env)
    path = os.path.join(CANONICAL_DIR, fname)
    if not os.path.exists(path):
        return []
    entries = []
    with open(path) as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))
    return entries


def append_to_canonical(
    new_entries: list[dict],
    env: str,
    source: str,
    dry_run: bool = False,
) -> dict:
    """Append validated, deduplicated entries to canonical file.

    Returns dict with counts and any issues found.
    """
    fname = _env_to_filename(env)
    path = os.path.join(CANONICAL_DIR, fname)

    # 1. Validate all new entries
    validation = validate_batch(new_entries, env)
    if validation["invalid"] > 0:
        return {
            "status": "rejected",
            "reason": f"{validation['invalid']}/{validation['total']} entries invalid",
            "issues": validation["issues"][:10],
        }

    # 2. Load existing entries and build fingerprint set
    existing = load_canonical(env)
    existing_fps = {_entry_fingerprint(e) for e in existing}

    # 3. Deduplicate
    unique = []
    dupes = 0
    for entry in new_entries:
        fp = _entry_fingerprint(entry)
        if fp in existing_fps:
            dupes += 1
        else:
            existing_fps.add(fp)
            # Ensure source field
            if "source" not in entry:
                entry["source"] = source
            unique.append(entry)

    if dry_run:
        return {
            "status": "dry_run",
            "would_append": len(unique),
            "duplicates_skipped": dupes,
            "new_total": len(existing) + len(unique),
        }

    # 4. Append to file
    if unique:
        with open(path, "a") as f:
            for entry in unique:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return {
        "status": "success",
        "appended": len(unique),
        "duplicates_skipped": dupes,
        "previous_count": len(existing),
        "new_total": len(existing) + len(unique),
    }


def upload_to_hf(env: str, token: Optional[str] = None) -> dict:
    """Upload a canonical file to HF repo."""
    try:
        from huggingface_hub import HfApi
    except ImportError:
        return {"status": "error", "reason": "huggingface_hub not installed"}

    token = token or os.environ.get("HF_TOKEN", "")
    if not token:
        return {"status": "error", "reason": "HF_TOKEN not set"}

    fname = _env_to_filename(env)
    local_path = os.path.join(CANONICAL_DIR, fname)
    remote_path = f"canonical/{fname}"

    api = HfApi(token=token)
    api.upload_file(
        path_or_fileobj=local_path,
        path_in_repo=remote_path,
        repo_id=HF_REPO,
        repo_type="dataset",
        commit_message=f"data: update canonical/{fname}",
    )
    return {"status": "success", "file": remote_path}


def upload_all_to_hf(token: Optional[str] = None) -> dict:
    """Upload all canonical files to HF."""
    results = {}
    for env in VALID_ROLES:
        results[env] = upload_to_hf(env, token)
    return results


def _env_to_filename(env: str) -> str:
    """Convert environment name to canonical filename."""
    mapping = {
        "GAME": "game.jsonl",
        "NAVWORLD": "navworld.jsonl",
        "SWE-SYNTH": "swe_synth.jsonl",
        "LIVEWEB": "liveweb.jsonl",
        "LGC-v2": "lgc_v2.jsonl",
        "PRINT": "print.jsonl",
    }
    return mapping.get(env, f"{env.lower().replace('-', '_')}.jsonl")


def full_audit() -> dict:
    """Run format audit on all canonical files. Returns per-env results."""
    results = {}
    for env in VALID_ROLES:
        entries = load_canonical(env)
        validation = validate_batch(entries, env)
        results[env] = {
            "count": len(entries),
            "valid": validation["valid"],
            "invalid": validation["invalid"],
            "status": "PASS" if validation["invalid"] == 0 else "FAIL",
        }
    return results
