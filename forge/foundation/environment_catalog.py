"""Explicit environment catalog for Layer 0 wiring.

The active architecture must not rely on import side effects or mutable global
registries to discover environments. This catalog is the explicit composition
root for environment definitions.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from forge.env.base import EnvProtocol
from forge.env.gem import GemEnv


@dataclass(frozen=True)
class EnvironmentDefinition:
    """Explicit pairing of data and GEM environment implementations."""

    name: str
    data_env: type[EnvProtocol]
    gem_env: type[GemEnv] | None = None


class EnvironmentCatalog:
    """Immutable environment catalog used by active execution paths."""

    def __init__(self, definitions: list[EnvironmentDefinition]):
        data_envs: dict[str, type[EnvProtocol]] = {}
        gem_envs: dict[str, type[GemEnv]] = {}

        for definition in definitions:
            if definition.name in data_envs:
                raise ValueError(f"duplicate environment definition: {definition.name}")
            data_envs[definition.name] = definition.data_env
            if definition.gem_env is not None:
                gem_envs[definition.name] = definition.gem_env

        self._data_envs = data_envs
        self._gem_envs = gem_envs

    def make_data(self, name: str) -> EnvProtocol:
        env_cls = self.get_data_class(name)
        if env_cls is None:
            available = ", ".join(self.list_data_envs())
            raise KeyError(f"Unknown env '{name}'. Available: {available}")
        return env_cls()

    def make_gem(self, name: str) -> GemEnv:
        gem_cls = self.get_gem_class(name)
        if gem_cls is None:
            available = ", ".join(self.list_gem_envs())
            raise KeyError(f"No GEM env '{name}'. Available: {available}")
        return gem_cls()

    def get_data_class(self, name: str) -> type[EnvProtocol] | None:
        return self._data_envs.get(name)

    def get_gem_class(self, name: str) -> type[GemEnv] | None:
        return self._gem_envs.get(name)

    def list_data_envs(self) -> list[str]:
        return sorted(self._data_envs.keys())

    def list_gem_envs(self) -> list[str]:
        return sorted(self._gem_envs.keys())

    def list_all(self) -> dict[str, list[str]]:
        return {
            "data": self.list_data_envs(),
            "gem": self.list_gem_envs(),
        }

    def has_data(self, name: str) -> bool:
        return name in self._data_envs

    def has_gem(self, name: str) -> bool:
        return name in self._gem_envs


@lru_cache(maxsize=1)
def default_environment_catalog() -> EnvironmentCatalog:
    """Return the explicit built-in environment catalog."""

    from forge.env.game import GameEnv, GameGemEnv
    from forge.env.lgc import LgcEnv, LgcGemEnv
    from forge.env.liveweb import LivewebEnv, LivewebGemEnv
    from forge.env.memorygym import MemorygymEnv
    from forge.env.navworld import NavworldEnv, NavworldGemEnv
    from forge.env.print_env import PrintEnv, PrintGemEnv
    from forge.env.swe import SweEnv, SweGemEnv

    return EnvironmentCatalog(
        definitions=[
            EnvironmentDefinition("GAME", GameEnv, GameGemEnv),
            EnvironmentDefinition("NAVWORLD", NavworldEnv, NavworldGemEnv),
            EnvironmentDefinition("SWE-INFINITE", SweEnv, SweGemEnv),
            EnvironmentDefinition("LIVEWEB", LivewebEnv, LivewebGemEnv),
            EnvironmentDefinition("MEMORYGYM", MemorygymEnv),
            EnvironmentDefinition("LGC-v2", LgcEnv, LgcGemEnv),
            EnvironmentDefinition("PRINT", PrintEnv, PrintGemEnv),
        ]
    )
