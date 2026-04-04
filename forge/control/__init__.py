"""Compatibility package for legacy `forge.control.*` submodule imports.

Primary implementations now live under `forge/core/*`.

This package intentionally does not re-export package-level symbols. Import the
needed submodules explicitly, for example:

- `forge.core.control.service`
- `forge.core.experiments`
- `forge.core.templates.registry`
- legacy compatibility submodules such as `forge.control.service`
"""

__all__: list[str] = []
