"""Control-plane experiment definitions and storage."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import Field, model_validator
import yaml

from forge.foundation.schema import JsonValue, StrictModel


class TrainingLifecycleState(str, Enum):
    DRAFT = "draft"
    PREPARED = "prepared"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINATED = "terminated"
    BLOCKED = "blocked"


class RunRecord(StrictModel):
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
    extra: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _fold_unknown_into_extra(cls, raw):
        if not isinstance(raw, dict):
            return raw
        known = {"training_run", "evaluation_run", "collect_run", "agent_eval", "extra"}
        extra = dict(raw.get("extra", {}))
        for key in list(raw.keys()):
            if key not in known:
                extra[key] = raw[key]
        raw = {key: value for key, value in raw.items() if key in known}
        raw["extra"] = extra
        return raw


class Experiment(StrictModel):
    """A single control-plane experiment definition."""

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


class ExperimentStore:
    """YAML-backed experiment registry for the control plane."""

    def __init__(self, experiments_dir: str = "experiments"):
        self.dir = Path(experiments_dir)

    def load(self, experiment_id: str) -> Experiment | None:
        for name in (
            f"{experiment_id}.yaml",
            f"{experiment_id}-draft.yaml",
            f"{experiment_id}-ab.yaml",
        ):
            path = self.dir / name
            if not path.exists():
                continue
            with path.open(encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
            data.setdefault("id", experiment_id)
            return Experiment.from_dict(data)
        return None

    def exists(self, experiment_id: str) -> bool:
        return self.load(experiment_id) is not None

    def save(self, experiment: Experiment) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / f"{experiment.id}.yaml"
        if path.exists():
            with path.open(encoding="utf-8") as handle:
                current_raw = yaml.safe_load(handle) or {}
            current_raw.setdefault("id", experiment.id)
            current = Experiment.from_dict(current_raw)
            experiment = self._merge_experiment(current, experiment)
        with path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(
                experiment.model_dump(mode="json"),
                handle,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )
        return path

    def _merge_experiment(self, current: Experiment, incoming: Experiment) -> Experiment:
        merged = self._merge_value((), current.model_dump(mode="json"), incoming.model_dump(mode="json"))
        return Experiment.from_dict(merged)

    def _merge_value(self, path: tuple[str, ...], current, incoming):
        if isinstance(current, dict) and isinstance(incoming, dict):
            merged: dict = {}
            for key in current.keys() | incoming.keys():
                if key in current and key in incoming:
                    merged[key] = self._merge_value(path + (str(key),), current[key], incoming[key])
                elif key in incoming:
                    merged[key] = incoming[key]
                else:
                    merged[key] = current[key]
            return merged

        if path == ("status",):
            return self._merge_lifecycle_status(current, incoming)

        if self._is_empty(incoming) and not self._is_empty(current):
            return current
        return incoming

    def _merge_lifecycle_status(self, current, incoming):
        if self._is_empty(incoming):
            return current
        if self._is_empty(current):
            return incoming
        order = {
            TrainingLifecycleState.DRAFT.value: 0,
            TrainingLifecycleState.PREPARED.value: 1,
            TrainingLifecycleState.RUNNING.value: 2,
            TrainingLifecycleState.BLOCKED.value: 3,
            TrainingLifecycleState.COMPLETED.value: 4,
            TrainingLifecycleState.FAILED.value: 4,
            TrainingLifecycleState.TERMINATED.value: 4,
        }
        current_value = str(current)
        incoming_value = str(incoming)
        return incoming if order.get(incoming_value, -1) >= order.get(current_value, -1) else current

    @staticmethod
    def _is_empty(value) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return value == ""
        if isinstance(value, (dict, list, tuple, set)):
            return len(value) == 0
        return False

    def list_experiments(self, status: str | None = None) -> list[Experiment]:
        experiments: list[Experiment] = []
        if not self.dir.exists():
            return experiments
        for path in sorted(self.dir.glob("*.yaml")):
            try:
                with path.open(encoding="utf-8") as handle:
                    data = yaml.safe_load(handle) or {}
            except Exception:
                continue
            data.setdefault("id", path.stem)
            experiment = Experiment.from_dict(data)
            if status is None or experiment.status.value == status or experiment.status == status:
                experiments.append(experiment)
        return experiments

    def update_status(self, experiment_id: str, status: str) -> bool:
        experiment = self.load(experiment_id)
        if experiment is None:
            return False
        experiment.status = TrainingLifecycleState(status)
        self.save(experiment)
        return True

    def next_experiment_id(self) -> str:
        experiments = self.list_experiments()
        if not experiments:
            return "v1"
        max_num = 0.0
        for experiment in experiments:
            try:
                number = float(experiment.id.replace("v", "").split("-")[0])
            except ValueError:
                continue
            max_num = max(max_num, number)
        return f"v{max_num + 0.01:.2f}"
