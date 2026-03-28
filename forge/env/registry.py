"""Compatibility wrappers over the explicit environment catalog.

Active architecture paths should depend on ``EnvironmentCatalog`` directly.
These wrappers remain only so older call sites can keep functioning while the
refactor moves code onto explicit catalog wiring.
"""

from __future__ import annotations

from typing import Optional

from forge.env.base import EnvProtocol
from forge.env.gem import GemEnv
from forge.foundation.environment_catalog import default_environment_catalog


class EnvRegistry:
    """Compatibility view over explicitly cataloged data environments."""

    _compat_envs: dict[str, type[EnvProtocol]] = {}

    @classmethod
    def register(cls, name: str):
        """Decorator for compatibility-only dynamic registrations."""

        def decorator(env_cls: type[EnvProtocol]):
            cls._compat_envs[name] = env_cls
            return env_cls
        return decorator

    @classmethod
    def _envs(cls) -> dict[str, type[EnvProtocol]]:
        envs = {
            name: default_environment_catalog().get_data_class(name)
            for name in default_environment_catalog().list_data_envs()
        }
        envs.update(cls._compat_envs)
        return envs

    @classmethod
    def make(cls, name: str, **kwargs) -> EnvProtocol:
        """Create a data environment instance by name."""
        envs = cls._envs()
        if name not in envs:
            available = ", ".join(sorted(envs.keys()))
            raise KeyError(f"Unknown env '{name}'. Available: {available}")
        return envs[name](**kwargs)

    @classmethod
    def get(cls, name: str) -> Optional[type[EnvProtocol]]:
        """Get environment class without instantiating."""
        return cls._envs().get(name)

    @classmethod
    def list_envs(cls) -> list[str]:
        """List known data environment names."""
        return sorted(cls._envs().keys())

    @classmethod
    def has(cls, name: str) -> bool:
        """Check whether a data environment exists."""
        return name in cls._envs()


class EnvHub:
    """Compatibility view over explicitly cataloged GEM environments."""

    _compat_gem_envs: dict[str, type[GemEnv]] = {}

    @classmethod
    def register_gem(cls, name: str):
        """Decorator for compatibility-only GEM registrations."""

        def decorator(gem_cls: type[GemEnv]):
            cls._compat_gem_envs[name] = gem_cls
            return gem_cls
        return decorator

    @classmethod
    def _gem_envs(cls) -> dict[str, type[GemEnv]]:
        envs = {
            name: default_environment_catalog().get_gem_class(name)
            for name in default_environment_catalog().list_gem_envs()
        }
        envs.update(cls._compat_gem_envs)
        return envs

    @classmethod
    def make_data(cls, name: str, **kwargs) -> EnvProtocol:
        """Create a data environment instance."""
        return default_environment_catalog().make_data(name, **kwargs)

    @classmethod
    def make_gem(cls, name: str, **kwargs) -> GemEnv:
        """Create a GEM environment instance."""
        envs = cls._gem_envs()
        if name not in envs:
            available = ", ".join(sorted(envs.keys()))
            raise KeyError(f"No GEM env '{name}'. Available: {available}")
        return envs[name](**kwargs)

    @classmethod
    def list_data_envs(cls) -> list[str]:
        """List known data environment names."""
        return default_environment_catalog().list_data_envs()

    @classmethod
    def list_gem_envs(cls) -> list[str]:
        """List known GEM environment names."""
        return sorted(cls._gem_envs().keys())

    @classmethod
    def list_all(cls) -> dict[str, list[str]]:
        """List data and GEM environments."""
        return {
            "data": cls.list_data_envs(),
            "gem": cls.list_gem_envs(),
        }

    @classmethod
    def has_gem(cls, name: str) -> bool:
        """Check whether a GEM environment exists."""
        return name in cls._gem_envs()
