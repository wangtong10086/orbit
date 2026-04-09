#!/usr/bin/env python3
"""Export a public release snapshot from the private development repository."""

from __future__ import annotations

import argparse
import fnmatch
import os
from pathlib import Path
import shutil
import subprocess
import sys

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


def _normalize(rel_path: str) -> str:
    normalized = Path(rel_path).as_posix()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _matches(path: str, patterns: list[str]) -> bool:
    normalized = _normalize(path)
    for pattern in patterns:
        pat = _normalize(pattern)
        if fnmatch.fnmatch(normalized, pat):
            return True
        if normalized == pat or normalized.startswith(f"{pat}/"):
            return True
    return False


def _copy_file(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def _copy_tree(src_root: Path, rel_path: str, dest_root: Path, excludes: list[str]) -> None:
    src = src_root / rel_path
    rel_norm = _normalize(rel_path)
    if _matches(rel_norm, excludes):
        return
    if src.is_file():
        _copy_file(src, dest_root / rel_norm)
        return
    if not src.is_dir():
        raise FileNotFoundError(f"Included path not found: {src}")
    for child in sorted(src.rglob("*")):
        child_rel = _normalize(str(child.relative_to(src_root)))
        if _matches(child_rel, excludes):
            continue
        if child.is_dir():
            (dest_root / child_rel).mkdir(parents=True, exist_ok=True)
            continue
        _copy_file(child, dest_root / child_rel)


def export_snapshot(*, repo_root: Path, manifest_path: Path, output_dir: Path, force: bool) -> None:
    manifest = _load_manifest(manifest_path)
    export = manifest["export"]
    includes: list[str] = export["include"]
    excludes: list[str] = export.get("exclude", [])
    overlays: dict[str, str] = export.get("overlays", {})

    if output_dir.exists():
        if not force:
            raise FileExistsError(f"Output directory exists: {output_dir}. Pass --force to replace it.")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for include in includes:
        _copy_tree(repo_root, include, output_dir, excludes)

    for child in sorted(output_dir.rglob("*"), reverse=True):
        child_rel = _normalize(str(child.relative_to(output_dir)))
        if not _matches(child_rel, excludes):
            continue
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        elif child.exists():
            child.unlink()

    for dest_rel, overlay_rel in overlays.items():
        overlay_src = repo_root / overlay_rel
        if not overlay_src.exists():
            raise FileNotFoundError(f"Overlay not found: {overlay_src}")
        _copy_file(overlay_src, output_dir / _normalize(dest_rel))


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


def git_publish(*, output_dir: Path, owner: str, name: str, branch: str, message: str, force_push: bool) -> None:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Export and optionally publish a public repository snapshot.")
    parser.add_argument("--manifest", default="release/public-export.yaml")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--force", action="store_true", help="Replace output directory if it exists.")
    parser.add_argument("--create-repo", action="store_true", help="Create the target GitHub repo if it does not exist.")
    parser.add_argument("--push", action="store_true", help="Initialize git in the export directory and push to GitHub.")
    parser.add_argument("--force-push", action="store_true", help="Force-push the exported snapshot.")
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

    export_snapshot(repo_root=repo_root, manifest_path=manifest_path, output_dir=output_dir, force=args.force)

    if args.create_repo:
        ensure_public_repo(owner=owner, name=name, visibility=visibility, description=description)
    if args.push:
        git_publish(
            output_dir=output_dir,
            owner=owner,
            name=name,
            branch=branch,
            message=args.message,
            force_push=args.force_push,
        )
    print(output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
