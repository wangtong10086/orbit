"""Environment abstraction layer (Layer 0).

Provides three separated interfaces following ROCK's architecture:
- Sandbox API: Runtime lifecycle management (start/stop/execute)
- GEM API: Interactive environment protocol (reset/step/close)
- Data API: Offline validation and cleaning for SFT data

The explicit EnvironmentCatalog is the active composition root.
EnvHub and EnvRegistry are compatibility wrappers for older call sites.
"""

from __future__ import annotations

from importlib import import_module

__all__ = [
    # Data validation (existing)
    "EnvProtocol", "EnvSpec", "EnvRegistry",
    "EnvironmentCatalog", "default_environment_catalog",
    # GEM protocol (new)
    "GemEnv", "Observation", "StepResult",
    # Sandbox API (new)
    "Sandbox", "SandboxConfig", "SandboxStatus",
    # Unified hub (new)
    "EnvHub",
]


_EXPORT_MAP = {
    "EnvProtocol": ("forge.env.base", "EnvProtocol"),
    "EnvSpec": ("forge.env.base", "EnvSpec"),
    "EnvRegistry": ("forge.env.registry", "EnvRegistry"),
    "EnvironmentCatalog": ("forge.foundation.environment_catalog", "EnvironmentCatalog"),
    "default_environment_catalog": ("forge.foundation.environment_catalog", "default_environment_catalog"),
    "GemEnv": ("forge.env.gem", "GemEnv"),
    "Observation": ("forge.env.gem", "Observation"),
    "StepResult": ("forge.env.gem", "StepResult"),
    "Sandbox": ("forge.env.sandbox", "Sandbox"),
    "SandboxConfig": ("forge.env.sandbox", "SandboxConfig"),
    "SandboxStatus": ("forge.env.sandbox", "SandboxStatus"),
    "EnvHub": ("forge.env.registry", "EnvHub"),
}


def __getattr__(name: str):
    if name not in _EXPORT_MAP:
        raise AttributeError(name)
    module_name, attr_name = _EXPORT_MAP[name]
    module = import_module(module_name)
    return getattr(module, attr_name)
