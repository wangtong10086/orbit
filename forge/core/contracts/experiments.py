"""Generic experiment and run-query contracts."""

from __future__ import annotations

from pydantic import Field

from forge.core.contracts.execution import JobKind
from forge.foundation.schema import FrozenModel, RequestContext


class CreateExperimentRequest(FrozenModel):
    variable: str
    hypothesis: str
    experiment_id: str = ""
    status: str = "draft"
    train_config: dict = Field(default_factory=dict)
    data_config: dict = Field(default_factory=dict)
    notes: str = ""
    context: RequestContext = Field(default_factory=RequestContext)


class RunQuery(FrozenModel):
    experiment_id: str
    run_kind: JobKind
    run_key: str = ""
    context: RequestContext = Field(default_factory=RequestContext)


class RunLogsQuery(FrozenModel):
    experiment_id: str
    run_kind: JobKind
    run_key: str = ""
    tail: int = 100
    context: RequestContext = Field(default_factory=RequestContext)


_RUN_RECORD_KEYS = {
    JobKind.TRAIN: "training_run",
    JobKind.EVAL: "evaluation_run",
    JobKind.COLLECT: "collect_run",
}


def run_record_key(run_kind: JobKind) -> str:
    return _RUN_RECORD_KEYS[run_kind]


def resolve_run_record_key(run_kind: JobKind, run_key: str = "") -> str:
    return run_key or run_record_key(run_kind)
