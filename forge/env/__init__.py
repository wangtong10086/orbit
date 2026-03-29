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
    "EnvProtocol": ("forge.env.base", "EnvProtocol"),
    "EnvSpec": ("forge.env.base", "EnvSpec"),
    "EnvironmentCatalog": ("forge.foundation.environment_catalog", "EnvironmentCatalog"),
    "default_environment_catalog": ("forge.foundation.environment_catalog", "default_environment_catalog"),
    "GemEnv": ("forge.env.gem", "GemEnv"),
    "Observation": ("forge.env.gem", "Observation"),
    "StepResult": ("forge.env.gem", "StepResult"),
    "Sandbox": ("forge.env.sandbox", "Sandbox"),
    "SandboxConfig": ("forge.env.sandbox", "SandboxConfig"),
    "SandboxStatus": ("forge.env.sandbox", "SandboxStatus"),
}


def __getattr__(name: str):
    if name not in _EXPORT_MAP:
        raise AttributeError(name)
    module_name, attr_name = _EXPORT_MAP[name]
    module = import_module(module_name)
    return getattr(module, attr_name)
