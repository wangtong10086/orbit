"""Migration shim that delegates MemoryGym plugin wiring to the env pack."""

from __future__ import annotations

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_SRC = REPO_ROOT / "packages" / "env_memorygym" / "src"
BUNDLE_INPUTS = REPO_ROOT


def _prepend_python_path(path: Path) -> None:
    if path.exists() and str(path) not in sys.path:
        sys.path.insert(0, str(path))


_prepend_python_path(PACKAGE_SRC)

# In remote training bundles, env packs are staged under bundle/inputs/runtime-package-*.
# Prefer the staged package over any image-installed wheel so the plugin resolves the
# exact env-pack source shipped with the run.
for candidate in sorted(BUNDLE_INPUTS.glob("runtime-package-*")):
    candidate_src = candidate / "src"
    if (candidate_src / "orbit_env_memorygym").exists():
        _prepend_python_path(candidate_src)
        break

from orbit_env_memorygym.api import register_ms_swift_plugin


register_ms_swift_plugin()
