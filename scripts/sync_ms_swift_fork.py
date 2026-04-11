#!/usr/bin/env python3
"""Sync the installed ms-swift source tree into the local ORBIT fork."""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import shutil
from typing import Iterable

from apply_ms_swift_patches import apply_patches


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _default_target_root() -> Path:
    return _repo_root() / "packages" / "affine_ms_swift" / "vendor" / "ms_swift_fork"


def _installed_swift_root() -> Path:
    spec = importlib.util.find_spec("swift")
    if spec is None or spec.origin is None:
        raise SystemExit("Could not locate installed swift package in the current interpreter")
    return Path(spec.origin).resolve().parent


def _ignore(_path: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        if name == "__pycache__" or name.endswith((".pyc", ".pyo")):
            ignored.add(name)
    return ignored


def sync_ms_swift_fork(
    *,
    source_root: Path,
    target_root: Path,
    apply_orbit_patches: bool = True,
) -> dict[str, object]:
    target_swift = target_root / "swift"
    target_root.mkdir(parents=True, exist_ok=True)
    if target_swift.exists():
        shutil.rmtree(target_swift)
    shutil.copytree(source_root, target_swift, ignore=_ignore)

    patched_files: list[str] = []
    if apply_orbit_patches:
        patched_files = [str(path.relative_to(target_root)) for path in apply_patches(target_swift)]

    upstream_version = importlib.metadata.version("ms-swift")
    manifest = {
        "upstream_project": "ms-swift",
        "upstream_version": upstream_version,
        "fork_project": "affine-ms-swift-fork",
        "fork_version": f"{upstream_version}+affine.1",
        "source_root": str(source_root),
        "python_path_entry": str(target_root),
        "patched_files": patched_files,
        "patch_source": "scripts/apply_ms_swift_patches.py",
    }
    (target_root / "FORK_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", default=None, help="Path to an installed swift package root")
    parser.add_argument("--target-root", default=str(_default_target_root()), help="Fork root to sync into")
    parser.add_argument("--skip-patches", action="store_true", help="Do not apply ORBIT patchset to the fork")
    args = parser.parse_args()

    source_root = Path(args.source_root).expanduser().resolve() if args.source_root else _installed_swift_root()
    target_root = Path(args.target_root).expanduser().resolve()
    manifest = sync_ms_swift_fork(
        source_root=source_root,
        target_root=target_root,
        apply_orbit_patches=not args.skip_patches,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
