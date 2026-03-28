"""Data pipeline — generate, clean, validate, store SFT data.

Composes Environment (validation/cleaning) + Prompt (template loading)
+ Canonical storage into a unified data flow.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from forge.foundation.environment_catalog import EnvironmentCatalog, default_environment_catalog


@dataclass
class IngestReport:
    """Results of a data ingestion batch."""

    accepted: int = 0
    dropped: int = 0
    invalid: int = 0
    duplicate: int = 0
    details: list[tuple[str, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.accepted + self.dropped + self.invalid + self.duplicate

    def summary(self) -> str:
        return (
            f"Ingested: {self.accepted}/{self.total} "
            f"(dropped={self.dropped}, invalid={self.invalid}, dup={self.duplicate})"
        )


class DataPipeline:
    """High-level data pipeline for a single environment.

    Usage:
        pipe = DataPipeline("NAVWORLD")
        report = pipe.ingest(raw_records)
        pipe.export("/tmp/navworld_sft.jsonl")
    """

    def __init__(self, env_name: str, catalog: EnvironmentCatalog | None = None):
        self.catalog = catalog or default_environment_catalog()
        self.env = self.catalog.make_data(env_name)
        self._store: list[dict] = []

    def ingest(self, entries: list[dict]) -> IngestReport:
        """Clean, validate, and store a batch of records.

        Flow: raw → env.clean_entry() → env.validate_entry() → dedup → store
        """
        report = IngestReport()
        seen_hashes = set()

        for entry in entries:
            # Clean
            cleaned = self.env.clean_entry(entry)
            if cleaned is None:
                report.dropped += 1
                report.details.append(("dropped", "clean_entry returned None"))
                continue

            # Validate
            issues = self.env.validate_entry(cleaned)
            if issues:
                report.invalid += 1
                report.details.append(("invalid", "; ".join(issues)))
                continue

            # Dedup (by content hash)
            import hashlib
            import json
            content_hash = hashlib.md5(
                json.dumps(cleaned.get("messages", []), sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()
            if content_hash in seen_hashes:
                report.duplicate += 1
                report.details.append(("duplicate", content_hash[:12]))
                continue
            seen_hashes.add(content_hash)

            self._store.append(cleaned)
            report.accepted += 1

        return report

    def export(self, path: str) -> int:
        """Export stored records to JSONL file. Returns record count."""
        import json
        with open(path, "w") as f:
            for record in self._store:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return len(self._store)

    def deep_validate(self) -> dict:
        """Run deep validation on all stored records."""
        return self.env.deep_validate(self._store)

    @property
    def count(self) -> int:
        return len(self._store)

    def clear(self) -> None:
        self._store.clear()
