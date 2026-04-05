"""Shared Pydantic schema foundation for active module boundaries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Generic, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue


PayloadT = TypeVar("PayloadT")


class StrictModel(BaseModel):
    """Strict default model for all cross-module contracts."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        arbitrary_types_allowed=True,
        use_enum_values=False,
    )


class FrozenModel(StrictModel):
    """Immutable value object base."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        arbitrary_types_allowed=True,
        frozen=True,
        use_enum_values=False,
    )


class RequestContext(StrictModel):
    actor: str = "system"
    source: str = "internal"
    correlation_id: str = Field(default_factory=lambda: str(uuid4()))
    reason: str = ""


class ValidationIssue(StrictModel):
    loc: tuple[str, ...] = ()
    msg: str
    kind: str = "value_error"


class SchemaErrorResponse(StrictModel):
    error: str = "validation_error"
    issues: list[ValidationIssue]


class VersionedDocument(StrictModel, Generic[PayloadT]):
    schema_version: str = "v1"
    payload: PayloadT


def dump_json_document(path: str | Path, payload: BaseModel, *, schema_version: str = "v1") -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        VersionedDocument[dict](schema_version=schema_version, payload=payload.model_dump(mode="json")).model_dump_json(
            indent=2
        )
        + "\n",
        encoding="utf-8",
    )


def load_json_document(path: str | Path) -> dict:
    target = Path(path)
    return json.loads(target.read_text(encoding="utf-8"))
