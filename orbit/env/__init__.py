"""Environment abstraction layer (Layer 0).

Provides three separated interfaces:
- Sandbox API: runtime lifecycle management
- GEM API: interactive environment protocol
- Data API: offline validation and cleaning for SFT data

The explicit EnvironmentCatalog is the only active composition root.
"""

from __future__ import annotations

from importlib import import_module

__all__ = [
    # Data validation
    "EnvProtocol", "EnvSpec",
    "EnvironmentCatalog", "default_environment_catalog",
    # GEM protocol
    "GemEnv", "Observation", "StepResult",
    # Sandbox API
    "Sandbox", "SandboxConfig", "SandboxStatus",
]


_EXPORT_MAP = {
    "EnvProtocol": ("orbit.env.base", "EnvProtocol"),
    "EnvSpec": ("orbit.env.base", "EnvSpec"),
    "EnvironmentCatalog": ("orbit.foundation.environment_catalog", "EnvironmentCatalog"),
    "default_environment_catalog": ("orbit.foundation.environment_catalog", "default_environment_catalog"),
    "GemEnv": ("orbit.env.gem", "GemEnv"),
    "Observation": ("orbit.env.gem", "Observation"),
    "StepResult": ("orbit.env.gem", "StepResult"),
    "Sandbox": ("orbit.env.sandbox", "Sandbox"),
    "SandboxConfig": ("orbit.env.sandbox", "SandboxConfig"),
    "SandboxStatus": ("orbit.env.sandbox", "SandboxStatus"),
}


def __getattr__(name: str):
    if name not in _EXPORT_MAP:
        raise AttributeError(name)
    module_name, attr_name = _EXPORT_MAP[name]
    module = import_module(module_name)
    return getattr(module, attr_name)
