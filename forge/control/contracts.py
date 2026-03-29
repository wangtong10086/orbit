"""Control-plane contracts."""

from __future__ import annotations

from pydantic import Field

from forge.execution.contracts import (
    CollectArtifactsRequest,
    CollectTaskSpec,
    DockerTarget,
    EvalTaskSpec,
    JobKind,
    RunLogsRequest,
    RunStatusRequest,
    RuntimeTarget,
    SshTarget,
    TargonTarget,
    TerminateRunRequest,
)
from forge.foundation.schema import FrozenModel, RequestContext


class ControlSubmissionTarget(FrozenModel):
    target: RuntimeTarget


class CreateExperimentRequest(FrozenModel):
    variable: str
    hypothesis: str
    experiment_id: str = ""
    status: str = "draft"
    train_config: dict = Field(default_factory=dict)
    data_config: dict = Field(default_factory=dict)
    notes: str = ""
    context: RequestContext = Field(default_factory=RequestContext)


class RenderTrainRequest(FrozenModel):
    experiment_id: str
    dataset_path: str
    bundle_dir: str | None = None
    context: RequestContext = Field(default_factory=RequestContext)


class SubmitTrainRequest(FrozenModel):
    experiment_id: str
    dataset_path: str
    submission_target: ControlSubmissionTarget
    bundle_dir: str | None = None
    context: RequestContext = Field(default_factory=RequestContext)


class RenderEvalRequest(FrozenModel):
    experiment_id: str
    spec: EvalTaskSpec
    bundle_dir: str | None = None
    context: RequestContext = Field(default_factory=RequestContext)


class SubmitEvalRequest(FrozenModel):
    experiment_id: str
    spec: EvalTaskSpec
    submission_target: ControlSubmissionTarget
    bundle_dir: str | None = None
    context: RequestContext = Field(default_factory=RequestContext)


class RenderCollectRequest(FrozenModel):
    experiment_id: str
    spec: CollectTaskSpec
    bundle_dir: str | None = None
    context: RequestContext = Field(default_factory=RequestContext)


class SubmitCollectRequest(FrozenModel):
    experiment_id: str
    spec: CollectTaskSpec
    submission_target: ControlSubmissionTarget
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
