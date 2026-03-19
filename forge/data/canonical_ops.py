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


# ============================================================================
# Quality filtering — keep only high-value data for training
# ============================================================================

def filter_by_seq_len(entries: list[dict], max_chars: int) -> tuple[list[dict], int]:
    """Filter entries that exceed estimated token limit.

    Returns (kept_entries, rejected_count).
    """
    kept = []
    rejected = 0
    for e in entries:
        chars = sum(len(m.get("content", "") or "") for m in e.get("messages", []))
        if chars <= max_chars:
            kept.append(e)
        else:
            rejected += 1
    return kept, rejected


def filter_game_quality(entries: list[dict],
                        max_per_solved: int = 500,
                        max_per_zero_tier: int = 100,
                        min_unique_thinks: int = 2) -> tuple[list[dict], dict]:
    """Filter GAME entries by quality criteria.

    Returns (kept_entries, reject_reasons).
    """
    import collections

    solved_games = {"goofspiel"}
    zero_tier = {"othello", "hex", "clobber"}
    game_counts = collections.Counter()
    kept = []
    reasons = collections.Counter()

    for e in entries:
        game = e.get("game", "unknown")
        msgs = e.get("messages", [])

        # Trivial filter: too few messages
        if len(msgs) <= 4 and game != "leduc_poker":
            reasons["trivial"] += 1
            continue

        # Think diversity filter
        thinks = set()
        for m in msgs:
            c = m.get("content", "")
            if "<think>" in c and "</think>" in c:
                thinks.add(c.split("<think>")[1].split("</think>")[0][:80])
        if len(thinks) < min_unique_thinks and len(msgs) > 6:
            reasons["low_think_diversity"] += 1
            continue

        # Cap solved games
        if game in solved_games and game_counts[game] >= max_per_solved:
            reasons["solved_oversample"] += 1
            continue

        # Cap zero-tier games
        if game in zero_tier and game_counts[game] >= max_per_zero_tier:
            reasons["zero_tier_cap"] += 1
            continue

        kept.append(e)
        game_counts[game] += 1

    return kept, dict(reasons)


def filter_navworld_templates(entries: list[dict],
                              max_per_template: int = 200) -> tuple[list[dict], int]:
    """Downsample NAVWORLD entries by tool-call sequence pattern.

    Keeps top entries per template ranked by plan length.
    Returns (kept_entries, rejected_count).
    """
    import collections

    groups = collections.defaultdict(list)
    for e in entries:
        seq = []
        for m in e.get("messages", []):
            c = m.get("content", "")
            for part in c.split("<tool_call>"):
                if '"name": "' in part:
                    seq.append(part.split('"name": "')[1].split('"')[0])
        groups[" → ".join(seq)].append(e)

    kept = []
    rejected = 0
    for seq_str, group in groups.items():
        group.sort(
            key=lambda e: len(e["messages"][-1].get("content", "")),
            reverse=True,
        )
        kept.extend(group[:max_per_template])
        rejected += max(0, len(group) - max_per_template)

    return kept, rejected


# ============================================================================
# Normalization — convert raw generation output to canonical schema
# ============================================================================

def normalize_entry(entry: dict) -> dict:
    """Normalize an entry to canonical schema: (role, content) only.

    Handles:
    - Flattening tool_calls to <tool_call> tags
    - Converting content=None to ""
    - Removing extra message fields (tool_call_id, etc.)
    """
    new_entry = {k: v for k, v in entry.items() if k != "messages"}
    new_msgs = []
    for msg in entry.get("messages", []):
        new_msg = {"role": msg["role"], "content": msg.get("content", "") or ""}

        if "tool_calls" in msg and msg["tool_calls"]:
            parts = []
            for tc in msg["tool_calls"]:
                fn = tc["function"]
                parts.append(
                    f'<tool_call>\n{{"name": "{fn["name"]}", '
                    f'"arguments": {fn["arguments"]}}}\n</tool_call>'
                )
            new_msg["content"] = "\n".join(parts)

        new_msgs.append(new_msg)

    new_entry["messages"] = new_msgs
    return new_entry


def load_staging_file(path: str) -> list[dict]:
    """Load entries from a staging JSONL file."""
    entries = []
    with open(path) as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))
    return entries


def ingest_staging(
    staging_path: str,
    env: str,
    source: str,
    normalize: bool = True,
    upload: bool = True,
    dry_run: bool = False,
) -> dict:
    """Full pipeline: load staging → normalize → validate → append → HF upload.

    This is the primary entry point for adding new data to canonical.
    """
    # 1. Load
    entries = load_staging_file(staging_path)
    if not entries:
        return {"status": "error", "reason": f"no entries in {staging_path}"}

    # 2. Normalize
    if normalize:
        entries = [normalize_entry(e) for e in entries]

    # 3. Append (includes validation + dedup)
    result = append_to_canonical(entries, env, source, dry_run=dry_run)

    # 4. Upload to HF
    if upload and not dry_run and result.get("status") == "success" and result.get("appended", 0) > 0:
        hf_result = upload_to_hf(env)
        result["hf_upload"] = hf_result

    return result


# ============================================================================
# CLI
# ============================================================================

def main():
    """CLI entry point for canonical data operations."""
    import argparse

    parser = argparse.ArgumentParser(description="Canonical data operations")
    sub = parser.add_subparsers(dest="cmd")

    # audit
    sub.add_parser("audit", help="Run full format audit on all canonical files")

    # ingest
    p_ingest = sub.add_parser("ingest", help="Ingest staging file into canonical")
    p_ingest.add_argument("file", help="Path to staging JSONL file")
    p_ingest.add_argument("--env", required=True, help="Environment name")
    p_ingest.add_argument("--source", default="staging", help="Source label")
    p_ingest.add_argument("--no-normalize", action="store_true")
    p_ingest.add_argument("--no-upload", action="store_true")
    p_ingest.add_argument("--dry-run", action="store_true")

    # upload
    p_upload = sub.add_parser("upload", help="Upload canonical file(s) to HF")
    p_upload.add_argument("--env", help="Environment (or 'all')")

    args = parser.parse_args()

    if args.cmd == "audit":
        results = full_audit()
        for env, r in results.items():
            status = "✅" if r["status"] == "PASS" else "❌"
            print(f"  {status} {env}: {r['count']} entries, {r['valid']} valid, {r['invalid']} invalid")

    elif args.cmd == "ingest":
        result = ingest_staging(
            args.file, args.env, args.source,
            normalize=not args.no_normalize,
            upload=not args.no_upload,
            dry_run=args.dry_run,
        )
        print(json.dumps(result, indent=2))

    elif args.cmd == "upload":
        if args.env == "all":
            results = upload_all_to_hf()
            for env, r in results.items():
                print(f"  {env}: {r['status']}")
        elif args.env:
            result = upload_to_hf(args.env)
            print(json.dumps(result, indent=2))
        else:
            print("Specify --env ENV or --env all")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
