"""Explicit monorepo path wiring for internal package roots."""

from __future__ import annotations

from pathlib import Path
import sys


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def monorepo_package_src_dirs() -> tuple[Path, ...]:
    root = repo_root()
    return (
        root / "packages" / "affine_ms_swift" / "vendor" / "ms_swift_fork",
        root / "packages" / "rl_runtime" / "src",
        root / "packages" / "affine_ms_swift" / "src",
        root / "packages" / "env_memorygym" / "src",
        root / "packages" / "env_affinetes" / "src",
    )


def ensure_monorepo_package_paths() -> tuple[Path, ...]:
    package_dirs = tuple(path for path in monorepo_package_src_dirs() if path.exists())
    for package_dir in reversed(package_dirs):
        if str(package_dir) not in sys.path:
            sys.path.insert(0, str(package_dir))
    return package_dirs


__all__ = ["ensure_monorepo_package_paths", "monorepo_package_src_dirs", "repo_root"]
