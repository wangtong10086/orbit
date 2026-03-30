"""Environment protocol and base types.

Defines two separated interfaces following ROCK's architecture:
- EnvProtocol: Data validation and cleaning (offline SFT data pipeline)
- GemEnv: Interactive environment protocol (make/reset/step/close) — see gem.py
- Sandbox: Runtime lifecycle management — see sandbox.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from forge.foundation.data_contracts import validate_canonical_entry


@dataclass
class EnvSpec:
    """Environment metadata — shared by both data and GEM layers."""

    name: str
    version: str = "1.0"
    task_count: int = 200
    completeness_threshold: float = 0.8
    scoring_weight: float = 1.0
    valid_roles: set[str] = field(default_factory=lambda: {"system", "user", "assistant"})
    allowed_extra_fields: set[str] = field(default_factory=set)
    terminal_roles: set[str] = field(default_factory=lambda: {"assistant"})


class EnvProtocol:
    """Data validation protocol — validates and cleans SFT training data.

    This is the offline data pipeline interface. For interactive
    environment interaction, see GemEnv in forge.env.gem.
    For runtime management, see Sandbox in forge.env.sandbox.

    Every environment must implement validate_entry() and clean_entry().
    """

    spec: EnvSpec

    def validate_entry(self, entry: dict) -> list[str]:
        """Validate a single data entry. Returns list of issues (empty = valid).

        Checks message schema, roles, required fields etc.
        """
        _, issues = validate_canonical_entry(entry, env_spec=self.spec, expected_env=self.spec.name)
        return [issue.msg for issue in issues]

    def clean_entry(self, record: dict) -> Optional[dict]:
        """Clean a single data entry. Returns None to discard.

        Override in subclasses for env-specific cleaning logic.
        """
        return record

    def deep_validate(self, records: list[dict]) -> dict:
        """Deep quality audit on a batch of records. Returns summary stats.

        Override in subclasses for env-specific deep validation.
        """
        total = len(records)
        valid = sum(1 for r in records if not self.validate_entry(r))
        return {"total": total, "valid": valid, "invalid": total - valid}

    def prompt_builder(self):
        """Return a PromptBuilder pre-configured for this environment.

        Lazy import to avoid circular dependency with forge.prompt.
        """
        from forge.prompt.builder import PromptBuilder
        return PromptBuilder(self.spec.name)
