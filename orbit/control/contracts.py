"""Compatibility control-plane contracts over the generic core task submission model."""

from __future__ import annotations

from pydantic import Field

from orbit.core.contracts.experiments import CreateExperimentRequest, RunLogsQuery, RunQuery, run_record_key
from orbit.core.contracts.templates import ExecutionOverrides
from orbit.foundation.schema import FrozenModel, RequestContext
from orbit.tasks.collection.specs import CollectTaskSpec
from orbit.tasks.evaluation.specs import EvalTaskSpec


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


__all__ = [
    "CreateExperimentRequest",
    "ExecutionOverrides",
    "PrepareCollectRequest",
    "PrepareEvalRequest",
    "PrepareTrainRequest",
    "RunLogsQuery",
    "RunQuery",
    "SubmitCollectRequest",
    "SubmitEvalRequest",
    "SubmitTrainRequest",
    "run_record_key",
]
