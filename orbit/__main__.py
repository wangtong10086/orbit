"""Allow running orbit as: python3 -m orbit

Auto-bootstraps PYTHONPATH so no manual env setup needed.
"""
import sys
import os
from pathlib import Path

# Auto-detect project root and .pylibs
_root = Path(__file__).resolve().parent.parent
_pylibs = _root / ".pylibs"
for p in [str(_root), str(_pylibs)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from orbit.cli import main

main()
