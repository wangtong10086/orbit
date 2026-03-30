"""Canonical data operations — validate, append, sync to HF.

Single entry point for all canonical data mutations. Ensures format
consistency, deduplication, and HF sync on every change.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Optional

from forge.data.aggregate import dataset_repo_id, publish_mixed_dataset
from forge.config import ForgeConfig
from forge.foundation.audit import AuditEvent, AuditWriter
from forge.foundation.data_contracts import (
    CanonicalSyncReport,
    CollectPipelineReport,
    CollectedRawArtifact,
    IngestReport,
    PublishReport,
    RepoSyncReport,
    validate_canonical_entry,
)
from forge.foundation.environment_catalog import default_environment_catalog
from forge.foundation.repository import (
    LocalCanonicalRepository,
    canonical_fingerprint,
    env_to_filename,
)
from forge.foundation.schema import RequestContext
from forge.pipeline.data import DataIngestPipeline


CANONICAL_DIR = "data/canonical"


CATALOG = default_environment_catalog()
AUDIT = AuditWriter()


def _resolve_token(token: Optional[str] = None) -> str:
    return token or os.environ.get("HF_TOKEN", "")


def _resolve_repo(repo_id: Optional[str] = None) -> str:
    return dataset_repo_id(repo_id or ForgeConfig.load().hf_dataset_repo)


def _entry_fingerprint(entry: dict) -> str:
    """MD5 of all message contents for deduplication."""
    return canonical_fingerprint(entry)


def validate_entry(entry: dict, expected_env: str) -> list[str]:
    """Validate a single entry. Returns list of issues (empty = valid)."""
    _, issues = validate_canonical_entry(
        entry,
        env_spec=CATALOG.make_data(expected_env).spec if CATALOG.has_data(expected_env) else None,
        expected_env=expected_env,
    )
    return [issue.msg for issue in issues]


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


def load_canonical(env: str, canonical_dir: str = CANONICAL_DIR) -> list[dict]:
    """Load all entries from a canonical file."""
    return LocalCanonicalRepository(canonical_dir).load(env)


def append_to_canonical(
    new_entries: list[dict],
    env: str,
    source: str,
    dry_run: bool = False,
    canonical_dir: str = CANONICAL_DIR,
) -> IngestReport:
    """Append validated, deduplicated entries to canonical file.

    Returns dict with counts and any issues found.
    """
    repository = LocalCanonicalRepository(canonical_dir)
    pipeline = DataIngestPipeline(env, repository=repository, catalog=CATALOG)

    sanitized_entries = [normalize_entry(entry) for entry in new_entries]
    validation = validate_batch(sanitized_entries, env)
    if validation["invalid"] > 0:
        return IngestReport(
            status="rejected",
            reason=f"{validation['invalid']}/{validation['total']} entries invalid",
            issues=validation["issues"][:10],
        )

    existing = repository.load(env)
    existing_fps = {_entry_fingerprint(e) for e in existing}
    incoming_unique = []
    dupes = 0
    batch_fps: set[str] = set()
    for entry in sanitized_entries:
        fp = _entry_fingerprint(entry)
        if fp in existing_fps or fp in batch_fps:
            dupes += 1
            continue
        batch_fps.add(fp)
        incoming_unique.append(entry)

    if dry_run:
        return IngestReport(
            status="dry_run",
            appended=0,
            would_append=len(incoming_unique),
            duplicates_skipped=dupes,
            new_total=len(existing) + len(incoming_unique),
        )

    report = pipeline.ingest(sanitized_entries, source=source)
    AUDIT.write_event(
        AuditEvent[dict | None, dict | None].build(
            context=RequestContext(actor="system", source="data.canonical_ops"),
            entity_type="canonical",
            entity_id=env,
            action="canonical_ingested",
            request={"env": env, "source": source, "count": len(new_entries)},
            result=report.model_dump(mode="json"),
        )
    )

    return report.model_copy(
        update={
            "status": "success",
            "previous_count": len(existing),
            "new_total": len(existing) + report.accepted,
        }
    )


def upload_to_hf(
    env: str,
    token: Optional[str] = None,
    repo_id: Optional[str] = None,
    canonical_dir: str = CANONICAL_DIR,
) -> CollectedRawArtifact:
    """Upload a canonical file to HF repo."""
    try:
        from huggingface_hub import HfApi
    except ImportError:
        return CollectedRawArtifact(status="error", reason="huggingface_hub not installed")

    token = _resolve_token(token)
    if not token:
        return CollectedRawArtifact(status="error", reason="HF_TOKEN not set")

    fname = _env_to_filename(env)
    local_path = os.path.join(canonical_dir, fname)
    remote_path = f"canonical/{fname}"
    target_repo = _resolve_repo(repo_id)

    api = HfApi(token=token)
    api.upload_file(
        path_or_fileobj=local_path,
        path_in_repo=remote_path,
        repo_id=target_repo,
        repo_type="dataset",
        commit_message=f"data: update canonical/{fname}",
    )
    result = CollectedRawArtifact(status="success", file=remote_path)
    AUDIT.write_event(
        AuditEvent[dict | None, dict | None].build(
            context=RequestContext(actor="system", source="data.canonical_ops"),
            entity_type="canonical",
            entity_id=env,
            action="canonical_upload_completed",
            request={"env": env, "repo_id": target_repo},
            result=result.model_dump(mode="json"),
        )
    )
    return result


def upload_all_to_hf(
    token: Optional[str] = None,
    repo_id: Optional[str] = None,
    canonical_dir: str = CANONICAL_DIR,
) -> dict[str, CollectedRawArtifact]:
    """Upload all canonical files to HF."""
    results = {}
    for env in CATALOG.list_data_envs():
        results[env] = upload_to_hf(env, token=token, repo_id=repo_id, canonical_dir=canonical_dir)
    return results


def _env_to_filename(env: str) -> str:
    """Convert environment name to canonical filename."""
    return env_to_filename(env)


def full_audit(canonical_dir: str = CANONICAL_DIR) -> dict:
    """Run format audit on all canonical files. Returns per-env results."""
    results = {}
    for env in CATALOG.list_data_envs():
        entries = load_canonical(env, canonical_dir=canonical_dir)
        validation = validate_batch(entries, env)
        results[env] = {
            "count": len(entries),
            "valid": validation["valid"],
            "invalid": validation["invalid"],
            "status": "PASS" if validation["invalid"] == 0 else "FAIL",
        }
    return results


def hf_sync_repo(
    repo_id: Optional[str] = None,
    local_dir: str = ".hf-sync",
    prefixes: tuple[str, ...] = ("raw/", "canonical/", "README.md"),
    token: Optional[str] = None,
) -> RepoSyncReport:
    """Download selected paths from an HF datasets repo into a local workspace."""

    try:
        from huggingface_hub import HfApi, hf_hub_download
    except ImportError as exc:
        raise RuntimeError("huggingface_hub is required for HF repo sync") from exc

    target_repo = _resolve_repo(repo_id)
    api = HfApi(token=_resolve_token(token) or None)
    files = api.list_repo_files(repo_id=target_repo, repo_type="dataset")
    target_root = Path(local_dir)
    target_root.mkdir(parents=True, exist_ok=True)

    downloaded = []
    for path_in_repo in files:
        if prefixes and not any(
            path_in_repo == prefix or path_in_repo.startswith(prefix)
            for prefix in prefixes
        ):
            continue
        local_path = hf_hub_download(
            repo_id=target_repo,
            filename=path_in_repo,
            repo_type="dataset",
            token=_resolve_token(token) or None,
        )
        dest = target_root / path_in_repo
        dest.parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(Path(local_path).read_bytes())
        downloaded.append(str(dest))

    return RepoSyncReport(status="success", repo_id=target_repo, downloaded=downloaded)


def download_from_hf(
    env: str,
    token: Optional[str] = None,
    repo_id: Optional[str] = None,
    canonical_dir: str = CANONICAL_DIR,
) -> CanonicalSyncReport:
    """Download a canonical file from HF if it exists."""

    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise RuntimeError("huggingface_hub is required for HF canonical sync") from exc

    target_repo = _resolve_repo(repo_id)
    canonical_root = Path(canonical_dir)
    canonical_root.mkdir(parents=True, exist_ok=True)
    fname = _env_to_filename(env)
    remote_path = f"canonical/{fname}"
    local_path = canonical_root / fname

    try:
        downloaded = hf_hub_download(
            repo_id=target_repo,
            filename=remote_path,
            repo_type="dataset",
            token=_resolve_token(token) or None,
        )
        local_path.write_bytes(Path(downloaded).read_bytes())
        return CanonicalSyncReport(status="success", env=env, path=str(local_path), repo_id=target_repo)
    except Exception as exc:
        local_path.touch(exist_ok=True)
        return CanonicalSyncReport(
            status="missing",
            env=env,
            path=str(local_path),
            repo_id=target_repo,
            reason=str(exc),
        )


def upload_raw_file(
    local_path: str,
    env: str,
    token: Optional[str] = None,
    repo_id: Optional[str] = None,
    remote_name: str | None = None,
) -> CollectedRawArtifact:
    """Upload a preserved raw collection artifact to HF datasets storage."""

    try:
        from huggingface_hub import HfApi
    except ImportError as exc:
        raise RuntimeError("huggingface_hub is required for raw uploads") from exc

    token = _resolve_token(token)
    if not token:
        return CollectedRawArtifact(status="error", reason="HF_TOKEN not set")

    source = Path(local_path)
    target_repo = _resolve_repo(repo_id)
    env_slug = env.lower().replace("-", "_")
    path_in_repo = f"raw/{env_slug}/{remote_name or source.name}"
    api = HfApi(token=token)
    api.upload_file(
        path_or_fileobj=str(source),
        path_in_repo=path_in_repo,
        repo_id=target_repo,
        repo_type="dataset",
        commit_message=f"data: preserve raw {env_slug} artifact",
    )
    result = CollectedRawArtifact(status="success", file=path_in_repo)
    AUDIT.write_event(
        AuditEvent[dict | None, dict | None].build(
            context=RequestContext(actor="system", source="data.canonical_ops"),
            entity_type="raw_artifact",
            entity_id=f"{env}:{source.name}",
            action="raw_uploaded",
            request={"env": env, "repo_id": target_repo},
            result=result.model_dump(mode="json"),
        )
    )
    return result


def upload_dataset_card(
    repo_id: Optional[str] = None,
    token: Optional[str] = None,
    dataset_config: str = "mixed",
    split: str = "train",
) -> CollectedRawArtifact:
    """Upload a dataset card with explicit config metadata for HF viewers."""

    try:
        from huggingface_hub import HfApi
    except ImportError as exc:
        raise RuntimeError("huggingface_hub is required for dataset card uploads") from exc

    token = _resolve_token(token)
    if not token:
        return CollectedRawArtifact(status="error", reason="HF_TOKEN not set")

    target_repo = _resolve_repo(repo_id)
    content = "\n".join(
        [
            "---",
            "configs:",
            f"  - config_name: {dataset_config}",
            "    data_files:",
            f"      - split: {split}",
            f"        path: mixed/*.parquet",
            "---",
            "",
            "# EVA Mixed Dataset",
            "",
            "This repo stores three layers of data:",
            "",
            "- `raw/`: preserved collection outputs",
            "- `canonical/`: validated per-environment canonical JSONL files",
            f"- `{dataset_config}`: viewer-friendly mixed dataset for training",
            "",
            "Recommended usage:",
            "",
            "```python",
            "from datasets import load_dataset",
            f'ds = load_dataset("{target_repo}", "{dataset_config}", split="{split}")',
            "```",
            "",
        ]
    )
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as handle:
        handle.write(content)
        temp_path = handle.name

    api = HfApi(token=token)
    api.upload_file(
        path_or_fileobj=temp_path,
        path_in_repo="README.md",
        repo_id=target_repo,
        repo_type="dataset",
        commit_message="docs: update dataset card",
    )
    Path(temp_path).unlink(missing_ok=True)
    return CollectedRawArtifact(status="success", file="README.md")


def publish_mixed(
    token: Optional[str] = None,
    repo_id: Optional[str] = None,
    canonical_dir: str = CANONICAL_DIR,
    output_dir: str | None = None,
    config_name: str = "mixed",
    split: str = "train",
    envs: list[str] | None = None,
    min_score: float = 0.0,
    max_samples_per_env: int = 0,
) -> PublishReport:
    """Build and publish the mixed viewer-friendly dataset plus README."""

    token = _resolve_token(token)
    if not token:
        return PublishReport(status="error", reason="HF_TOKEN not set")
    target_repo = _resolve_repo(repo_id)
    result = publish_mixed_dataset(
        token=token,
        repo_id=target_repo,
        canonical_dir=canonical_dir,
        output_dir=output_dir,
        config_name=config_name,
        split=split,
        envs=envs,
        min_score=min_score,
        max_samples_per_env=max_samples_per_env,
    )
    card_result = upload_dataset_card(
        repo_id=target_repo,
        token=token,
        dataset_config=config_name,
        split=split,
    )
    report = result.model_copy(update={"dataset_card": card_result})
    AUDIT.write_event(
        AuditEvent[dict | None, dict | None].build(
            context=RequestContext(actor="system", source="data.canonical_ops"),
            entity_type="mixed_dataset",
            entity_id=target_repo,
            action="mixed_published",
            request={"repo_id": target_repo, "config": config_name, "split": split},
            result=report.model_dump(mode="json"),
        )
    )
    return report


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
    import collections, re

    groups = collections.defaultdict(list)
    name_pattern = re.compile(r'"name":\s*"([^"]+)"')
    for e in entries:
        seq = []
        for m in e.get("messages", []):
            c = m.get("content", "")
            if "<tool_call>" in c:
                seq.extend(name_pattern.findall(c))
        # Normalize to ordered unique sequence for grouping
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
    """Normalize an entry to canonical schema without model-specific packing."""

    new_entry = {k: v for k, v in entry.items() if k != "messages"}
    new_msgs = []
    for msg in entry.get("messages", []):
        new_msg = {
            "role": msg["role"],
            "content": msg.get("content", "") or "",
        }
        for key in ("tool_calls", "tool_call_id", "tools"):
            if key in msg and msg[key] is not None:
                new_msg[key] = msg[key]
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
    canonical_dir: str = CANONICAL_DIR,
    repo_id: Optional[str] = None,
    token: Optional[str] = None,
) -> IngestReport:
    """Full pipeline: load staging → normalize → validate → append → HF upload.

    This is the primary entry point for adding new data to canonical.
    """
    # 1. Load
    entries = load_staging_file(staging_path)
    if not entries:
        return IngestReport(status="error", reason=f"no entries in {staging_path}")

    # 2. Normalize
    if normalize:
        entries = [normalize_entry(e) for e in entries]

    # 3. Append (includes validation + dedup)
    result = append_to_canonical(entries, env, source, dry_run=dry_run, canonical_dir=canonical_dir)

    # 4. Upload to HF
    if upload and not dry_run and result.status == "success" and result.appended > 0:
        hf_result = upload_to_hf(env, token=token, repo_id=repo_id, canonical_dir=canonical_dir)
        result = result.model_copy(update={"hf_upload": hf_result})

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
        print(json.dumps(result.model_dump(mode="json"), indent=2))

    elif args.cmd == "upload":
        if args.env == "all":
            results = upload_all_to_hf()
            for env, r in results.items():
                print(f"  {env}: {r.status}")
        elif args.env:
            result = upload_to_hf(args.env)
            print(json.dumps(result.model_dump(mode="json"), indent=2))
        else:
            print("Specify --env ENV or --env all")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
