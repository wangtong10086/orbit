"""Data pipeline — generate, clean, validate, store SFT data."""

from __future__ import annotations

from pathlib import Path
import json

from orbit.foundation.contracts import ConversationPacker
from orbit.foundation.data_contracts import (
    DatasetBuildReport,
    IngestDetail,
    IngestReport,
    validate_canonical_entry,
)
from orbit.foundation.environment_catalog import EnvironmentCatalog, default_environment_catalog
from orbit.foundation.packing import IdentityConversationPacker
from orbit.foundation.repository import LocalCanonicalRepository, canonical_fingerprint


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
            model, schema_issues = validate_canonical_entry(
                entry,
                env_spec=self.env.spec,
                expected_env=self.env_name,
            )
            if schema_issues or model is None:
                report = report.model_copy(
                    update={
                        "invalid": report.invalid + 1,
                        "details": report.details
                        + [
                            IngestDetail(
                                kind="invalid",
                                message="; ".join(issue.msg for issue in schema_issues) or "schema validation failed",
                            )
                        ],
                    }
                )
                continue

            cleaned = self.env.clean_entry(dict(entry))
            if cleaned is None:
                report = report.model_copy(
                    update={
                        "dropped": report.dropped + 1,
                        "details": report.details + [IngestDetail(kind="dropped", message="clean_entry returned None")],
                    }
                )
                continue

            fingerprint = canonical_fingerprint(cleaned)
            if fingerprint in existing or fingerprint in batch_fingerprints:
                report = report.model_copy(
                    update={
                        "duplicates_skipped": report.duplicates_skipped + 1,
                        "details": report.details + [IngestDetail(kind="duplicate", message=fingerprint[:12])],
                    }
                )
                continue

            batch_fingerprints.add(fingerprint)
            if "source" not in cleaned:
                cleaned["source"] = source
            accepted_records.append(cleaned)
            report = report.model_copy(update={"appended": report.appended + 1})

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
                report = report.model_copy(
                    update={
                        "by_env": {**report.by_env, env_name: written},
                        "total": report.total + written,
                    }
                )

        return report
