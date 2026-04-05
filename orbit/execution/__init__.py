"""Compatibility package for legacy `orbit.execution.*` submodule imports.

Primary implementations now live under `orbit/core/execution/*` and
`orbit/core/contracts/execution.py`.

This package intentionally does not re-export package-level symbols. Import the
needed submodules explicitly, for example:

- `orbit.core.execution.bundle`
- `orbit.core.execution.service`
- `orbit.core.contracts.execution`
- legacy compatibility submodules such as `orbit.execution.service`
"""

__all__: list[str] = []
