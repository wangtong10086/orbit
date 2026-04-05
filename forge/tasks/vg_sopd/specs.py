"""Typed specs for the VG-SOPD workflow and its stage tasks."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import Field, model_validator

from forge.core.contracts.execution import EnvKey, ResourceRequest
from forge.foundation.schema import FrozenModel, JsonValue, StrictModel
from forge.tasks.evaluation.specs import EvalTaskSpec
from forge.tasks.training.launch_config import (
    DatasetSource,
    ExecutionTarget,
    ExperimentLaunchSpec,
    HuggingFaceDatasetSource,
    LocalDatasetSource,
)
from forge.training.config import SwiftConfig


class StageExecutionSpec(StrictModel):
    template_id: str
    bundle_dir: str = ""
    image: str = ""
    detach: bool = False
    runtime_env: dict[str, str] = Field(default_factory=dict)
    resources: ResourceRequest = Field(default_factory=ResourceRequest)
    target: ExecutionTarget | None = None
    poll_interval_seconds: float = 1.0
    timeout_seconds: float = 900.0
    collect_artifacts: bool = True


class StageTrainingSpec(StrictModel):
    enabled: bool = True
    label: str = "sft"
    train_config: SwiftConfig = Field(default_factory=SwiftConfig)
    execution: StageExecutionSpec


class ColdStartSpec(StrictModel):
    enabled: bool = False
    dataset: DatasetSource | None = None
    training: StageTrainingSpec | None = None

    @model_validator(mode="after")
    def _validate_enabled_shape(self):
        if self.enabled and self.dataset is None:
            raise ValueError("cold_start.dataset is required when cold_start.enabled=true")
        if self.enabled and self.training is None:
            raise ValueError("cold_start.training is required when cold_start.enabled=true")
        return self


class TeacherEndpointSpec(StrictModel):
    name: str
    kind: Literal["specialized", "white_box", "black_box"]
    enabled: bool = True
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class EnvironmentTeacherPolicy(StrictModel):
    primary: str = ""
    fallbacks: tuple[str, ...] = ()


class TeacherPolicySpec(StrictModel):
    teachers: tuple[TeacherEndpointSpec, ...] = ()
    env_policies: dict[EnvKey, EnvironmentTeacherPolicy] = Field(default_factory=dict)


class FrontierRolloutSpec(StrictModel):
    samples_per_task: int = 2
    max_tasks: int = 0
    seed: int = 0
    temperature: float = 0.7
    require_student_prefix: bool = True
    task_id_field: str = "task_id"
    prompt_field: str = "prompt"
    expected_answer_field: str = "expected_answer"
    student_candidates_field: str = "student_candidates"
    teacher_repair_field: str = "teacher_repair"
    metadata_field: str = "metadata"
    execution: StageExecutionSpec


class RelabelSpec(StrictModel):
    success_threshold: float = 0.99
    near_miss_threshold: float = 0.5
    preference_margin: float = 0.05
    annotate_first_error: bool = True
    execution: StageExecutionSpec


class CompileSpec(StrictModel):
    compiler_recipe_version: str = "vg_sopd_v1"
    include_gkd_when_available: bool = True
    max_positive_ratio: float = 1.0
    execution: StageExecutionSpec


class GuardrailEvalSpec(StrictModel):
    enabled: bool = False
    command: tuple[str, ...] = ()
    prompts_path: str = ""
    output_filename: str = "guardrail_eval.json"

    @model_validator(mode="after")
    def _validate_enabled_shape(self):
        if self.enabled and not self.command:
            raise ValueError("guardrails.command is required when guardrails.enabled=true")
        return self


class VGSopdEvaluationSpec(StrictModel):
    enabled: bool = False
    spec: EvalTaskSpec | None = None
    execution: StageExecutionSpec | None = None

    @model_validator(mode="after")
    def _validate_enabled_shape(self):
        if self.enabled and self.spec is None:
            raise ValueError("evaluation.spec is required when evaluation.enabled=true")
        if self.enabled and self.execution is None:
            raise ValueError("evaluation.execution is required when evaluation.enabled=true")
        return self


class ArtifactLineage(FrozenModel):
    stage: str
    run_key: str
    bundle_path: str
    artifacts: dict[str, str] = Field(default_factory=dict)
    logs: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class IterationReport(FrozenModel):
    iteration_index: int
    model_revision_in: str
    model_revision_out: str = ""
    stage_metrics: dict[str, JsonValue] = Field(default_factory=dict)
    artifacts: tuple[ArtifactLineage, ...] = ()
    guardrail_before: dict[str, JsonValue] = Field(default_factory=dict)
    guardrail_after: dict[str, JsonValue] = Field(default_factory=dict)


class FrontierTaskSpec(FrozenModel):
    experiment_id: str
    iteration_index: int
    student_model_revision: str
    task_source_path: str
    environments: tuple[EnvKey, ...]
    rollout: FrontierRolloutSpec


class RelabelTaskSpec(FrozenModel):
    experiment_id: str
    iteration_index: int
    model_revision: str
    frontier_traces_path: str
    environments: tuple[EnvKey, ...]
    teacher_policy: TeacherPolicySpec
    relabel: RelabelSpec


class CompileTaskSpec(FrozenModel):
    experiment_id: str
    iteration_index: int
    model_revision: str
    relabelled_traces_path: str
    teacher_augmented_traces_path: str
    environments: tuple[EnvKey, ...]
    compile: CompileSpec


class VGSopdLaunchConfig(StrictModel):
    version: int = 1
    kind: Literal["vg_sopd_launch"] = "vg_sopd_launch"
    required_env: tuple[str, ...] = ()
    experiment: ExperimentLaunchSpec
    student_model_revision: str
    environments: tuple[EnvKey, ...]
    frontier_task_source: DatasetSource
    teacher_policy: TeacherPolicySpec = Field(default_factory=TeacherPolicySpec)
    cold_start: ColdStartSpec = Field(default_factory=ColdStartSpec)
    frontier: FrontierRolloutSpec
    relabel: RelabelSpec
    compile: CompileSpec
    sft_stage: StageTrainingSpec
    preference_stage: StageTrainingSpec
    gkd_stage: StageTrainingSpec | None = None
    evaluation: VGSopdEvaluationSpec = Field(default_factory=VGSopdEvaluationSpec)
    guardrails: GuardrailEvalSpec = Field(default_factory=GuardrailEvalSpec)
    iteration_count: int = 1
    output_root: str = "artifacts/vg_sopd"


def load_vg_sopd_launch_config(path: str | Path) -> VGSopdLaunchConfig:
    target = Path(path)
    with target.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    return VGSopdLaunchConfig.model_validate(payload)


__all__ = [
    "ArtifactLineage",
    "ColdStartSpec",
    "CompileSpec",
    "CompileTaskSpec",
    "EnvironmentTeacherPolicy",
    "FrontierRolloutSpec",
    "FrontierTaskSpec",
    "GuardrailEvalSpec",
    "HuggingFaceDatasetSource",
    "IterationReport",
    "LocalDatasetSource",
    "RelabelSpec",
    "RelabelTaskSpec",
    "StageExecutionSpec",
    "StageTrainingSpec",
    "TeacherEndpointSpec",
    "TeacherPolicySpec",
    "VGSopdEvaluationSpec",
    "VGSopdLaunchConfig",
    "load_vg_sopd_launch_config",
]
