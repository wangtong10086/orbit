"""Shared audit models and writer utilities."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Generic, TypeVar
from uuid import uuid4
import hashlib
import json

from pydantic import Field

from forge.foundation.schema import RequestContext, StrictModel


RequestT = TypeVar("RequestT")
ResultT = TypeVar("ResultT")
SnapshotT = TypeVar("SnapshotT")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuditEvent(StrictModel, Generic[RequestT, ResultT]):
    event_id: str = ""
    timestamp: str = ""
    actor: str
    source: str
    correlation_id: str
    entity_type: str
    entity_id: str
    action: str
    request: RequestT | None = None
    result: ResultT | None = None
    status: str = "ok"

    @classmethod
    def build(
        cls,
        *,
        context: RequestContext,
        entity_type: str,
        entity_id: str,
        action: str,
        request=None,
        result=None,
        status: str = "ok",
    ) -> "AuditEvent":
        return cls(
            event_id=str(uuid4()),
            timestamp=utc_now_iso(),
            actor=context.actor,
            source=context.source,
            correlation_id=context.correlation_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            request=request,
            result=result,
            status=status,
        )


class AuditSnapshot(StrictModel, Generic[SnapshotT]):
    entity_type: str
    entity_id: str
    schema_version: str = "v1"
    version: str
    payload: SnapshotT
    payload_hash: str
    source_event_id: str
    timestamp: str = Field(default_factory=utc_now_iso)


class AuditWriter:
    """Append-only event and snapshot writer."""

    def __init__(self, root: str | Path = "logs/audit"):
        self.root = Path(root)

    def _events_path(self, event: AuditEvent) -> Path:
        day = event.timestamp[:10]
        return self.root / "events" / f"{day}.jsonl"

    def _snapshot_path(self, snapshot: AuditSnapshot) -> Path:
        return self.root / "snapshots" / snapshot.entity_type / snapshot.entity_id / f"{snapshot.version}.json"

    def write_event(self, event: AuditEvent) -> Path:
        path = self._events_path(event)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(event.model_dump_json() + "\n")
        return path

    def write_snapshot(
        self,
        *,
        entity_type: str,
        entity_id: str,
        version: str,
        payload,
        source_event_id: str,
        schema_version: str = "v1",
    ) -> Path:
        payload_data = payload.model_dump(mode="json") if hasattr(payload, "model_dump") else payload
        payload_json = json.dumps(payload_data, ensure_ascii=False, sort_keys=True)
        snapshot = AuditSnapshot[dict](
            entity_type=entity_type,
            entity_id=entity_id,
            schema_version=schema_version,
            version=version,
            payload=payload_data,
            payload_hash=hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
            source_event_id=source_event_id,
        )
        path = self._snapshot_path(snapshot)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(snapshot.model_dump_json(indent=2) + "\n", encoding="utf-8")
        return path
