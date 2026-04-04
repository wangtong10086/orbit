"""Control-plane contracts."""

from __future__ import annotations

from pydantic import Field

from forge.control.task_specs import CollectTaskSpec, EvalTaskSpec
from forge.control.templates import ExecutionOverrides
from forge.execution.contracts import JobKind
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


class PrepareTrainRequest(FrozenModel):
    experiment_id: str
    dataset_path: str
    bundle_dir: str | None = None
    context: RequestContext = Field(default_factory=RequestContext)


class SubmitTrainRequest(FrozenModel):
    experiment_id: str
    dataset_path: str
    template_id: str
    overrides: ExecutionOverrides = Field(default_factory=ExecutionOverrides)
    bundle_dir: str | None = None
    context: RequestContext = Field(default_factory=RequestContext)


class PrepareEvalRequest(FrozenModel):
    experiment_id: str
    spec: EvalTaskSpec
    bundle_dir: str | None = None
    context: RequestContext = Field(default_factory=RequestContext)


class SubmitEvalRequest(FrozenModel):
    experiment_id: str
    spec: EvalTaskSpec
    template_id: str
    overrides: ExecutionOverrides = Field(default_factory=ExecutionOverrides)
    bundle_dir: str | None = None
    context: RequestContext = Field(default_factory=RequestContext)


class PrepareCollectRequest(FrozenModel):
    experiment_id: str
    spec: CollectTaskSpec
    bundle_dir: str | None = None
    context: RequestContext = Field(default_factory=RequestContext)


class SubmitCollectRequest(FrozenModel):
    experiment_id: str
    spec: CollectTaskSpec
    template_id: str
    overrides: ExecutionOverrides = Field(default_factory=ExecutionOverrides)
    bundle_dir: str | None = None
    context: RequestContext = Field(default_factory=RequestContext)


class RunQuery(FrozenModel):
    experiment_id: str
    run_kind: JobKind
    context: RequestContext = Field(default_factory=RequestContext)


class RunLogsQuery(FrozenModel):
    experiment_id: str
    run_kind: JobKind
    tail: int = 100
    context: RequestContext = Field(default_factory=RequestContext)


_RUN_RECORD_KEYS = {
    JobKind.TRAIN: "training_run",
    JobKind.EVAL: "evaluation_run",
    JobKind.COLLECT: "collect_run",
}


def run_record_key(run_kind: JobKind) -> str:
    return _RUN_RECORD_KEYS[run_kind]
