"""Environment protocol and base types.

Defines two separated interfaces following ROCK's architecture:
- EnvProtocol: Data validation and cleaning (offline SFT data pipeline)
- GemEnv: Interactive environment protocol (make/reset/step/close) — see gem.py
- Sandbox: Runtime lifecycle management — see sandbox.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


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
        issues = []
        if "messages" not in entry:
            issues.append("missing 'messages' field")
            return issues
        if entry.get("env") != self.spec.name:
            issues.append(f"env='{entry.get('env')}' expected '{self.spec.name}'")
        if "score" not in entry:
            issues.append("missing 'score' field")

        msgs = entry["messages"]
        if len(msgs) < 2:
            issues.append(f"only {len(msgs)} messages (need ≥2)")

        for i, msg in enumerate(msgs):
            keys = set(msg.keys())
            missing = {"role", "content"} - keys
            extra = keys - {"role", "content"} - self.spec.allowed_extra_fields
            if extra:
                issues.append(f"msg[{i}]: extra fields {extra}")
            if missing:
                issues.append(f"msg[{i}]: missing fields {missing}")
            if msg.get("content") is None:
                issues.append(f"msg[{i}]: content is None")
            role = msg.get("role", "")
            if role not in self.spec.valid_roles:
                issues.append(f"msg[{i}]: role='{role}' not in {self.spec.valid_roles}")

        if msgs and msgs[-1].get("role") != "assistant":
            issues.append(f"last msg role='{msgs[-1].get('role')}' (must be assistant)")

        return issues

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
