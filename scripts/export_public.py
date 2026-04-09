#!/usr/bin/env python3
"""Export and publish a public release snapshot from the private repository."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import yaml


def _run(cmd: list[str], *, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def _load_manifest(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _dump_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _normalize(rel_path: str) -> str:
    normalized = Path(rel_path).as_posix()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _matching_patterns(path: str, patterns: list[str]) -> list[str]:
    normalized = _normalize(path)
    matches: list[str] = []
    for pattern in patterns:
        pat = _normalize(pattern)
        if fnmatch.fnmatch(normalized, pat):
            matches.append(pattern)
            continue
        if normalized == pat or normalized.startswith(f"{pat}/"):
            matches.append(pattern)
    return matches


def _matches(path: str, patterns: list[str]) -> bool:
    return bool(_matching_patterns(path, patterns))


def _copy_file(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def _record_excludes(report: dict, matched_patterns: list[str]) -> None:
    for pattern in matched_patterns:
        report.setdefault("exclude_hits", {}).setdefault(pattern, 0)
        report["exclude_hits"][pattern] += 1


def _copy_tree(
    src_root: Path,
    rel_path: str,
    dest_root: Path,
    excludes: list[str],
    *,
    report: dict,
) -> None:
    src = src_root / rel_path
    rel_norm = _normalize(rel_path)
    matched = _matching_patterns(rel_norm, excludes)
    if matched:
        _record_excludes(report, matched)
        return
    if src.is_file():
        _copy_file(src, dest_root / rel_norm)
        report.setdefault("include_hits", {}).setdefault(rel_norm, {"files": 0, "dirs": 0})
        report["include_hits"][rel_norm]["files"] += 1
        return
    if not src.is_dir():
        raise FileNotFoundError(f"Included path not found: {src}")
    report.setdefault("include_hits", {}).setdefault(rel_norm, {"files": 0, "dirs": 0})
    for child in sorted(src.rglob("*")):
        child_rel = _normalize(str(child.relative_to(src_root)))
        matched = _matching_patterns(child_rel, excludes)
        if matched:
            _record_excludes(report, matched)
            continue
        if child.is_dir():
            (dest_root / child_rel).mkdir(parents=True, exist_ok=True)
            report["include_hits"][rel_norm]["dirs"] += 1
            continue
        _copy_file(child, dest_root / child_rel)
        report["include_hits"][rel_norm]["files"] += 1


def _manifest_digest(manifest_path: Path) -> str:
    return hashlib.sha256(manifest_path.read_bytes()).hexdigest()


def _snapshot_counts(output_dir: Path) -> dict[str, int]:
    file_count = 0
    dir_count = 0
    for child in output_dir.rglob("*"):
        if child.is_dir():
            dir_count += 1
        elif child.is_file():
            file_count += 1
    return {"files": file_count, "dirs": dir_count}


def export_snapshot(*, repo_root: Path, manifest_path: Path, output_dir: Path, force: bool) -> dict:
    manifest = _load_manifest(manifest_path)
    export = manifest["export"]
    includes: list[str] = export["include"]
    excludes: list[str] = export.get("exclude", [])
    overlays: dict[str, str] = export.get("overlays", {})
    report: dict = {
        "manifest_path": str(manifest_path),
        "manifest_digest": _manifest_digest(manifest_path),
        "include_roots": includes,
        "exclude_patterns": excludes,
        "overlay_paths": overlays,
        "include_hits": {},
        "exclude_hits": {},
        "overlay_hits": {},
    }

    if output_dir.exists():
        if not force:
            raise FileExistsError(f"Output directory exists: {output_dir}. Pass --force to replace it.")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for include in includes:
        _copy_tree(repo_root, include, output_dir, excludes, report=report)

    for child in sorted(output_dir.rglob("*"), reverse=True):
        child_rel = _normalize(str(child.relative_to(output_dir)))
        matched = _matching_patterns(child_rel, excludes)
        if not matched:
            continue
        _record_excludes(report, matched)
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        elif child.exists():
            child.unlink()

    for dest_rel, overlay_rel in overlays.items():
        overlay_src = repo_root / overlay_rel
        if not overlay_src.exists():
            raise FileNotFoundError(f"Overlay not found: {overlay_src}")
        _copy_file(overlay_src, output_dir / _normalize(dest_rel))
        report["overlay_hits"][_normalize(dest_rel)] = _normalize(overlay_rel)

    report["snapshot"] = {
        "output_dir": str(output_dir),
        **_snapshot_counts(output_dir),
    }
    return report


def ensure_public_repo(*, owner: str, name: str, visibility: str, description: str) -> None:
    try:
        _run(["gh", "repo", "view", f"{owner}/{name}", "--json", "nameWithOwner"])
    except subprocess.CalledProcessError:
        cmd = [
            "gh",
            "repo",
            "create",
            f"{owner}/{name}",
            "--description",
            description,
            "--disable-wiki",
        ]
        if visibility == "public":
            cmd.append("--public")
        else:
            cmd.append("--private")
        _run(cmd)


def git_publish(
    *,
    output_dir: Path,
    owner: str,
    name: str,
    branch: str,
    message: str,
    force_push: bool,
) -> str:
    remote_url = os.environ.get("EXPORT_PUBLIC_REMOTE_URL", "").strip()
    if not remote_url:
        token = os.environ.get("EXPORT_PUBLIC_GIT_TOKEN", "").strip()
        if token:
            remote_url = f"https://x-access-token:{token}@github.com/{owner}/{name}.git"
        else:
            remote_url = f"git@github.com:{owner}/{name}.git"

    if not (output_dir / ".git").exists():
        _run(["git", "init", "-b", branch], cwd=output_dir)
    try:
        _run(["git", "remote", "get-url", "origin"], cwd=output_dir)
        _run(["git", "remote", "set-url", "origin", remote_url], cwd=output_dir)
    except subprocess.CalledProcessError:
        _run(["git", "remote", "add", "origin", remote_url], cwd=output_dir)

    _run(["git", "add", "-A", "--force", "."], cwd=output_dir)
    status = _run(["git", "status", "--short"], cwd=output_dir)
    if status:
        _run(["git", "commit", "-m", message], cwd=output_dir)
    push_cmd = ["git", "push", "-u", "origin", branch]
    if force_push:
        push_cmd.append("--force")
    _run(push_cmd, cwd=output_dir)
    return _run(["git", "rev-parse", "HEAD"], cwd=output_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export and optionally publish a public repository snapshot.")
    parser.add_argument("--manifest", default="release/public-export.yaml")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--force", action="store_true", help="Replace output directory if it exists.")
    parser.add_argument("--skip-export", action="store_true", help="Publish an existing snapshot directory without re-exporting.")
    parser.add_argument("--create-repo", action="store_true", help="Create the target GitHub repo if it does not exist.")
    parser.add_argument("--push", action="store_true", help="Initialize git in the export directory and push to GitHub.")
    parser.add_argument("--force-push", action="store_true", help="Force-push the exported snapshot.")
    parser.add_argument("--source-sha", default="", help="Explicit private source commit SHA to record in metadata.")
    parser.add_argument("--metadata-out", default="", help="Write snapshot/publish metadata to this JSON path.")
    parser.add_argument("--report-out", default="", help="Write export report JSON to this path.")
    parser.add_argument("--message", default="Public release snapshot")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    manifest_path = (repo_root / args.manifest).resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    manifest = _load_manifest(manifest_path)
    repo_cfg = manifest["repo"]
    owner = repo_cfg["owner"]
    name = repo_cfg["name"]
    visibility = repo_cfg.get("visibility", "public")
    branch = repo_cfg.get("default_branch", "main")
    description = repo_cfg.get("description", "")
    source_sha = args.source_sha.strip() or _run(["git", "rev-parse", "HEAD"], cwd=repo_root)

    if args.skip_export:
        if not output_dir.exists():
            raise FileNotFoundError(f"Snapshot directory does not exist: {output_dir}")
        report = {
            "manifest_path": str(manifest_path),
            "manifest_digest": _manifest_digest(manifest_path),
            "include_roots": manifest["export"]["include"],
            "exclude_patterns": manifest["export"].get("exclude", []),
            "overlay_paths": manifest["export"].get("overlays", {}),
            "include_hits": {},
            "exclude_hits": {},
            "overlay_hits": {},
            "snapshot": {
                "output_dir": str(output_dir),
                **_snapshot_counts(output_dir),
            },
        }
    else:
        report = export_snapshot(repo_root=repo_root, manifest_path=manifest_path, output_dir=output_dir, force=args.force)

    public_sha = ""
    if args.create_repo:
        ensure_public_repo(owner=owner, name=name, visibility=visibility, description=description)
    if args.push:
        public_sha = git_publish(
            output_dir=output_dir,
            owner=owner,
            name=name,
            branch=branch,
            message=args.message,
            force_push=args.force_push,
        )

    metadata = {
        "source_repo": _run(["git", "remote", "get-url", "origin"], cwd=repo_root),
        "source_sha": source_sha,
        "public_repo": f"{owner}/{name}",
        "public_branch": branch,
        "public_sha": public_sha,
        "export_manifest_digest": report["manifest_digest"],
        "snapshot_dir": str(output_dir),
    }
    if args.report_out:
        _dump_json(Path(args.report_out).expanduser().resolve(), report)
    if args.metadata_out:
        _dump_json(Path(args.metadata_out).expanduser().resolve(), metadata)
    print(output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
