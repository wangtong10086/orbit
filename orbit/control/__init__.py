"""Compatibility package for legacy `orbit.control.*` submodule imports.

Primary implementations now live under `orbit/core/*`.

This package intentionally does not re-export package-level symbols. Import the
needed submodules explicitly, for example:

- `orbit.core.control.service`
- `orbit.core.experiments`
- `orbit.core.templates.registry`
- legacy compatibility submodules such as `orbit.control.service`
"""

__all__: list[str] = []
