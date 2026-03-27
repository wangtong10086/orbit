"""Environment registry and EnvHub — discover and instantiate environments.

EnvRegistry: original registry for data validation environments (EnvProtocol).
EnvHub: unified hub managing both data validators and GEM environments,
analogous to ROCK's EnvHub for reproducible environment provisioning.
"""

from __future__ import annotations

from typing import Optional

from forge.env.base import EnvProtocol
from forge.env.gem import GemEnv


class EnvRegistry:
    """Global registry of data validation environment implementations."""

    _envs: dict[str, type[EnvProtocol]] = {}

    @classmethod
    def register(cls, name: str):
        """Decorator to register an environment class."""
        def decorator(env_cls: type[EnvProtocol]):
            cls._envs[name] = env_cls
            return env_cls
        return decorator

    @classmethod
    def make(cls, name: str, **kwargs) -> EnvProtocol:
        """Create an environment instance by name."""
        if name not in cls._envs:
            available = ", ".join(sorted(cls._envs.keys()))
            raise KeyError(f"Unknown env '{name}'. Available: {available}")
        return cls._envs[name](**kwargs)

    @classmethod
    def get(cls, name: str) -> Optional[type[EnvProtocol]]:
        """Get environment class without instantiating. Returns None if not found."""
        return cls._envs.get(name)

    @classmethod
    def list_envs(cls) -> list[str]:
        """List all registered environment names."""
        return sorted(cls._envs.keys())

    @classmethod
    def has(cls, name: str) -> bool:
        """Check if an environment is registered."""
        return name in cls._envs


class EnvHub:
    """Unified environment hub — manages both data and GEM environments.

    Analogous to ROCK's EnvHub: centralized registry for environment images
    that enables reproducible provisioning.

    Tracks two separate registries:
    - Data validators (EnvProtocol) via EnvRegistry
    - Interactive environments (GemEnv) via _gem_envs

    Usage:
        hub = EnvHub()
        # Data validation
        validator = hub.make_data("GAME")
        issues = validator.validate_entry(record)

        # GEM interaction
        gem_env = hub.make_gem("GAME")
        obs, info = gem_env.reset(seed=42)
    """

    _gem_envs: dict[str, type[GemEnv]] = {}

    @classmethod
    def register_gem(cls, name: str):
        """Decorator to register a GEM environment class."""
        def decorator(gem_cls: type[GemEnv]):
            cls._gem_envs[name] = gem_cls
            return gem_cls
        return decorator

    @classmethod
    def make_data(cls, name: str, **kwargs) -> EnvProtocol:
        """Create a data validation environment (delegates to EnvRegistry)."""
        return EnvRegistry.make(name, **kwargs)

    @classmethod
    def make_gem(cls, name: str, **kwargs) -> GemEnv:
        """Create a GEM interactive environment instance."""
        if name not in cls._gem_envs:
            available = ", ".join(sorted(cls._gem_envs.keys()))
            raise KeyError(f"No GEM env '{name}'. Available: {available}")
        return cls._gem_envs[name](**kwargs)

    @classmethod
    def list_data_envs(cls) -> list[str]:
        """List registered data validation environments."""
        return EnvRegistry.list_envs()

    @classmethod
    def list_gem_envs(cls) -> list[str]:
        """List registered GEM interactive environments."""
        return sorted(cls._gem_envs.keys())

    @classmethod
    def list_all(cls) -> dict[str, list[str]]:
        """List all registered environments by type."""
        return {
            "data": cls.list_data_envs(),
            "gem": cls.list_gem_envs(),
        }

    @classmethod
    def has_gem(cls, name: str) -> bool:
        """Check if a GEM environment is registered."""
        return name in cls._gem_envs
