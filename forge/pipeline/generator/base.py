"""Generator protocol — interface for environment-specific data generators.

Each generator knows how to produce training data for its environment.
Generators use the Environment layer for validation and the Prompt layer
for template management.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import Field

from forge.foundation.schema import JsonValue, StrictModel


class GeneratorRequest(StrictModel):
    count: int
    options: dict[str, JsonValue] = Field(default_factory=dict)


class GeneratorProtocol(Protocol):
    """Protocol for data generators.

    Each environment can have one or more generators that produce
    training records in the canonical format.
    """

    env_name: str

    def generate(self, request: GeneratorRequest) -> list[dict[str, JsonValue]]:
        """Generate training records."""
        ...

    def estimate_cost(self, n: int) -> dict:
        """Estimate cost/time for generating n records.

        Returns:
            Dict with keys like 'api_calls', 'estimated_cost_usd', 'estimated_time_minutes'
        """
        ...
