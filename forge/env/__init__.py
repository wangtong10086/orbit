"""Environment abstraction layer (Layer 0).

Provides three separated interfaces following ROCK's architecture:
- Sandbox API: Runtime lifecycle management (start/stop/execute)
- GEM API: Interactive environment protocol (reset/step/close)
- Data API: Offline validation and cleaning for SFT data

The explicit EnvironmentCatalog is the active composition root.
EnvHub and EnvRegistry are compatibility wrappers for older call sites.
"""

from forge.env.base import EnvProtocol, EnvSpec
from forge.env.gem import GemEnv, Observation, StepResult
from forge.env.registry import EnvRegistry, EnvHub
from forge.foundation.environment_catalog import EnvironmentCatalog, default_environment_catalog
from forge.env.sandbox import Sandbox, SandboxConfig, SandboxStatus

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
