"""Compatibility package for legacy `forge.execution.*` submodule imports.

Primary implementations now live under `forge/core/execution/*` and
`forge/core/contracts/execution.py`.

This package intentionally does not re-export package-level symbols. Import the
needed submodules explicitly, for example:

- `forge.core.execution.bundle`
- `forge.core.execution.service`
- `forge.core.contracts.execution`
- legacy compatibility submodules such as `forge.execution.service`
"""

__all__: list[str] = []
