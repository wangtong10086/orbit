"""Bundle storage and validation helpers for the execution plane."""

from __future__ import annotations

import json
from pathlib import Path
import shutil

from pydantic import BaseModel

from forge.foundation.audit import AuditWriter
from forge.execution.contracts import (
    ArtifactManifest,
    JobSpec,
    RunHandle,
    RunStatus,
)
from forge.foundation.schema import VersionedDocument


def _write_versioned(path: Path, payload: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = VersionedDocument[dict](schema_version="v1", payload=payload.model_dump(mode="json"))
    path.write_text(document.model_dump_json(indent=2) + "\n", encoding="utf-8")


def _read_payload(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    document = VersionedDocument[dict].model_validate(raw)
    return document.payload


class JobBundle:
    """On-disk job bundle.

    Layout:
      job.json
      inputs/
      scripts/entrypoint.sh
      artifacts/manifest.json
      runtime/
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.audit = AuditWriter()

    @property
    def job_path(self) -> Path:
        return self.path / "job.json"

    @property
    def inputs_dir(self) -> Path:
        return self.path / "inputs"

    @property
    def scripts_dir(self) -> Path:
        return self.path / "scripts"

    @property
    def artifacts_dir(self) -> Path:
        return self.path / "artifacts"

    @property
    def runtime_dir(self) -> Path:
        return self.path / "runtime"

    @property
    def entrypoint_path(self) -> Path:
        if self.job_path.exists():
            try:
                job = self.load_job()
                return self.path / job.entrypoint
            except Exception:
                pass
        return self.scripts_dir / "entrypoint.sh"

    @property
    def manifest_path(self) -> Path:
        return self.artifacts_dir / "manifest.json"

    @classmethod
    def create(cls, path: str | Path, overwrite: bool = False) -> "JobBundle":
        bundle = cls(path)
        if bundle.path.exists():
            if not overwrite:
                raise FileExistsError(f"Bundle already exists: {bundle.path}")
            shutil.rmtree(bundle.path)
        bundle.ensure_structure()
        bundle.write_manifest(ArtifactManifest())
        return bundle

    def ensure_structure(self) -> None:
        for subdir in (self.path, self.inputs_dir, self.scripts_dir, self.artifacts_dir, self.runtime_dir):
            subdir.mkdir(parents=True, exist_ok=True)

    def write_job(self, job: JobSpec) -> None:
        self.ensure_structure()
        _write_versioned(self.job_path, job)
        self.audit.write_snapshot(
            entity_type="job_spec",
            entity_id=job.job_id,
            version=str(int(self.job_path.stat().st_mtime_ns)),
            payload=job,
            source_event_id="bundle-local-write",
        )

    def load_job(self) -> JobSpec:
        return JobSpec.model_validate(_read_payload(self.job_path))

    def write_manifest(self, manifest: ArtifactManifest) -> None:
        _write_versioned(self.manifest_path, manifest)
        self.audit.write_snapshot(
            entity_type="artifact_manifest",
            entity_id=str(self.path),
            version=str(int(self.manifest_path.stat().st_mtime_ns)),
            payload=manifest,
            source_event_id="bundle-local-write",
        )

    def load_manifest(self) -> ArtifactManifest:
        return ArtifactManifest.model_validate(_read_payload(self.manifest_path))

    def copy_input(self, source_path: str, filename: str | None = None) -> str:
        src = Path(source_path)
        if not src.exists():
            raise FileNotFoundError(source_path)
        target_name = filename or src.name
        target = self.inputs_dir / target_name
        shutil.copy2(src, target)
        return str(target.relative_to(self.path))

    def write_text(self, relative_path: str, content: str, executable: bool = False) -> None:
        target = self.path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        if executable:
            target.chmod(target.stat().st_mode | 0o111)

    def validate(self) -> list[str]:
        issues: list[str] = []
        if not self.job_path.exists():
            issues.append("missing job.json")
        if not self.entrypoint_path.exists():
            issues.append("missing scripts/entrypoint.sh")
        if not self.manifest_path.exists():
            issues.append("missing artifacts/manifest.json")
        if self.job_path.exists():
            try:
                job = self.load_job()
            except Exception as exc:
                issues.append(f"invalid job.json: {exc}")
            else:
                for item in job.inputs:
                    if item.required and not (self.path / item.relative_path).exists():
                        issues.append(f"missing required input: {item.relative_path}")
        return issues

    def write_run_handle(self, handle: RunHandle) -> None:
        path = self.runtime_dir / "last_run.json"
        _write_versioned(path, handle)
        self.audit.write_snapshot(
            entity_type="run_handle",
            entity_id=handle.run_id,
            version=str(int(path.stat().st_mtime_ns)),
            payload=handle,
            source_event_id="bundle-local-write",
        )

    def load_run_handle(self) -> RunHandle:
        return RunHandle.model_validate(_read_payload(self.runtime_dir / "last_run.json"))

    def write_run_status(self, status: RunStatus) -> None:
        path = self.runtime_dir / "last_status.json"
        _write_versioned(path, status)
        self.audit.write_snapshot(
            entity_type="run_status",
            entity_id=status.run_id,
            version=str(int(path.stat().st_mtime_ns)),
            payload=status,
            source_event_id="bundle-local-write",
        )

    def load_run_status(self) -> RunStatus | None:
        path = self.runtime_dir / "last_status.json"
        if not path.exists():
            return None
        return RunStatus.model_validate(_read_payload(path))

    def update_manifest(self, manifest: ArtifactManifest) -> None:
        self.write_manifest(manifest)

    def record_local_artifacts(self) -> ArtifactManifest:
        logs: dict[str, str] = {}
        artifacts: dict[str, str] = {}
        for path in sorted(self.artifacts_dir.rglob("*")):
            if not path.is_file() or path == self.manifest_path:
                continue
            rel = str(path.relative_to(self.path))
            if path.suffix in {".log", ".out", ".err"}:
                logs[path.name] = rel
            else:
                artifacts[path.name] = rel
        manifest = ArtifactManifest(logs=logs, artifacts=artifacts)
        self.write_manifest(manifest)
        return manifest
