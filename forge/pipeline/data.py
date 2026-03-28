"""Data pipeline — generate, clean, validate, store SFT data.

Composes Environment (validation/cleaning) + Prompt (template loading)
+ Canonical storage into a unified data flow.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from forge.foundation.contracts import ConversationPacker
from forge.foundation.environment_catalog import EnvironmentCatalog, default_environment_catalog
from forge.foundation.packing import IdentityConversationPacker
from forge.foundation.repository import LocalCanonicalRepository, canonical_fingerprint


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


@dataclass
class DatasetBuildReport:
    """Results of building a training dataset from canonical data."""

    output_path: str
    total: int = 0
    by_env: dict[str, int] = field(default_factory=dict)


class DataIngestPipeline:
    """Repository-backed canonical ingest path."""

    def __init__(
        self,
        env_name: str,
        repository: LocalCanonicalRepository | None = None,
        catalog: EnvironmentCatalog | None = None,
    ):
        self.env_name = env_name
        self.catalog = catalog or default_environment_catalog()
        self.repository = repository or LocalCanonicalRepository()
        self.env = self.catalog.make_data(env_name)

    def ingest(
        self,
        entries: list[dict],
        source: str = "staging",
    ) -> IngestReport:
        report = IngestReport()
        existing = self.repository.fingerprint_set(self.env_name)
        batch_fingerprints: set[str] = set()
        accepted_records: list[dict] = []

        for entry in entries:
            cleaned = self.env.clean_entry(dict(entry))
            if cleaned is None:
                report.dropped += 1
                report.details.append(("dropped", "clean_entry returned None"))
                continue

            issues = self.env.validate_entry(cleaned)
            if issues:
                report.invalid += 1
                report.details.append(("invalid", "; ".join(issues)))
                continue

            fingerprint = canonical_fingerprint(cleaned)
            if fingerprint in existing or fingerprint in batch_fingerprints:
                report.duplicate += 1
                report.details.append(("duplicate", fingerprint[:12]))
                continue

            batch_fingerprints.add(fingerprint)
            if "source" not in cleaned:
                cleaned["source"] = source
            accepted_records.append(cleaned)
            report.accepted += 1

        if accepted_records:
            self.repository.append(self.env_name, accepted_records)

        return report


class DatasetBuildPipeline:
    """Build a training dataset from canonical repository entries."""

    def __init__(
        self,
        repository: LocalCanonicalRepository | None = None,
        packer: ConversationPacker | None = None,
        catalog: EnvironmentCatalog | None = None,
    ):
        self.repository = repository or LocalCanonicalRepository()
        self.packer = packer or IdentityConversationPacker()
        self.catalog = catalog or default_environment_catalog()

    def build(
        self,
        output_path: str,
        envs: list[str] | None = None,
        min_score: float = 0.0,
        max_per_env: int = 0,
    ) -> DatasetBuildReport:
        env_names = envs or self.catalog.list_data_envs()
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        report = DatasetBuildReport(output_path=output_path)
        with output.open("w", encoding="utf-8") as handle:
            for env_name in env_names:
                self.catalog.make_data(env_name)
                written = 0
                for record in self.repository.load(env_name):
                    if record.get("score", 0.0) < min_score:
                        continue
                    packed = self.packer.pack(record)
                    handle.write(json.dumps({"messages": packed}, ensure_ascii=False) + "\n")
                    written += 1
                    if max_per_env and written >= max_per_env:
                        break
                report.by_env[env_name] = written
                report.total += written

        return report


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
