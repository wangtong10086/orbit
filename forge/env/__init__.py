"""Environment abstraction layer (Layer 0).

Provides three separated interfaces following ROCK's architecture:
- Sandbox API: Runtime lifecycle management (start/stop/execute)
- GEM API: Interactive environment protocol (reset/step/close)
- Data API: Offline validation and cleaning for SFT data

EnvHub is the unified registry (analogous to ROCK's EnvHub).
EnvRegistry is kept for backward compatibility with data validation code.
"""

from forge.env.base import EnvProtocol, EnvSpec
from forge.env.gem import GemEnv, Observation, StepResult
from forge.env.registry import EnvRegistry, EnvHub
from forge.env.sandbox import Sandbox, SandboxConfig, SandboxStatus

__all__ = [
    # Data validation (existing)
    "EnvProtocol", "EnvSpec", "EnvRegistry",
    # GEM protocol (new)
    "GemEnv", "Observation", "StepResult",
    # Sandbox API (new)
    "Sandbox", "SandboxConfig", "SandboxStatus",
    # Unified hub (new)
    "EnvHub",
]
