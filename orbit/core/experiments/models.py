"""Experiment models for the core control kernel."""

from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from orbit.foundation.schema import JsonValue, StrictModel


class TrainingLifecycleState(str, Enum):
    DRAFT = "draft"
    PREPARED = "prepared"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINATED = "terminated"
    BLOCKED = "blocked"


class RunRecord(StrictModel):
    task_type: str = ""
    task_request: dict[str, JsonValue] = Field(default_factory=dict)
    task_summary: dict[str, JsonValue] = Field(default_factory=dict)
    bundle_path: str = ""
    runtime_kind: str = ""
    run_id: str = ""
    target_id: str = ""
    submitted_at: float | None = None
    template_id: str = ""
    template_snapshot: dict[str, JsonValue] = Field(default_factory=dict)
    execution_request: dict[str, JsonValue] = Field(default_factory=dict)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    status: str = ""
    status_detail: str = ""
    status_metadata: dict[str, JsonValue] = Field(default_factory=dict)
    logs: dict[str, str] = Field(default_factory=dict)
    artifacts: dict[str, str] = Field(default_factory=dict)
    artifact_metadata: dict[str, JsonValue] = Field(default_factory=dict)


class AgentEvaluationRecord(StrictModel):
    model_path: str
    geo_mean: float
    environments: dict[str, float] = Field(default_factory=dict)


class ExperimentResults(StrictModel):
    training_run: RunRecord | None = None
    evaluation_run: RunRecord | None = None
    collect_run: RunRecord | None = None
    agent_eval: AgentEvaluationRecord | None = None
    task_runs: dict[str, RunRecord] = Field(default_factory=dict)
    extra: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _fold_unknown_into_extra(cls, raw):
        if not isinstance(raw, dict):
            return raw
        known = {"training_run", "evaluation_run", "collect_run", "agent_eval", "task_runs", "extra"}
        extra = dict(raw.get("extra", {}))
        for key in list(raw.keys()):
            if key not in known:
                extra[key] = raw[key]
        raw = {key: value for key, value in raw.items() if key in known}
        raw["extra"] = extra
        return raw


class Experiment(StrictModel):
    id: str
    variable: str
    hypothesis: str
    status: TrainingLifecycleState = TrainingLifecycleState.DRAFT
    train_config: dict[str, JsonValue] = Field(default_factory=dict)
    data_config: dict[str, JsonValue] = Field(default_factory=dict)
    results: ExperimentResults = Field(default_factory=ExperimentResults)
    notes: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_shape(cls, raw):
        if not isinstance(raw, dict):
            return raw
        data = dict(raw)
        if "version" in data and "id" not in data:
            data["id"] = str(data["version"])
        status = str(data.get("status", "draft"))
        if status not in {item.value for item in TrainingLifecycleState}:
            data["status"] = "completed" if status in {"approved", "superseded"} else "draft"
        if "train_config" not in data and "config" in data:
            config = dict(data["config"])
            num_gpus = config.get("num_gpus", 1)
            if num_gpus == "auto":
                num_gpus = 1
            data["train_config"] = {
                "model": config.get("base_model", "Qwen/Qwen3-32B"),
                "learning_rate": config.get("lr", 1e-4),
                "lora_rank": config.get("lora_r", 64),
                "lora_alpha": config.get("lora_alpha", 128),
                "num_train_epochs": config.get("epochs", 1),
                "per_device_train_batch_size": config.get("batch_size", 2),
                "gradient_accumulation_steps": config.get("grad_accum", 8),
                "max_length": config.get("seq_len", 4096),
                "packing": config.get("packing", True),
                "num_gpus": num_gpus,
                "output_dir": config.get("output_dir", "/tmp/checkpoints"),
            }
        if "data_config" not in data and "data_mix" in data:
            data["data_config"] = {
                key: {"count": value}
                for key, value in dict(data["data_mix"]).items()
                if key != "total"
            }
        if "results" not in data:
            data["results"] = {}
        extra = dict(data.get("results", {}).get("extra", {})) if isinstance(data.get("results"), dict) else {}
        known = {"id", "variable", "hypothesis", "status", "train_config", "data_config", "results", "notes"}
        for key in list(data.keys()):
            if key not in known:
                extra[key] = data.pop(key)
        if isinstance(data.get("results"), dict):
            data["results"] = dict(data["results"])
            if extra:
                existing = dict(data["results"].get("extra", {}))
                existing.update(extra)
                data["results"]["extra"] = existing
        return data

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, raw: dict) -> "Experiment":
        return cls.model_validate(raw)
