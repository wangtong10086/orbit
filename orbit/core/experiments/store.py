"""Experiment persistence for the core control kernel."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import tempfile

import yaml

from orbit.core.experiments.models import Experiment, TrainingLifecycleState


class ExperimentStore:
    def __init__(self, experiments_dir: str = "experiments"):
        self.dir = Path(experiments_dir)

    @contextmanager
    def _lock(self, experiment_id: str):
        self.dir.mkdir(parents=True, exist_ok=True)
        lock_path = self.dir / f"{experiment_id}.lock"
        with lock_path.open("w", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

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
        with self._lock(experiment.id):
            if path.exists():
                with path.open(encoding="utf-8") as handle:
                    current_raw = yaml.safe_load(handle) or {}
                current_raw.setdefault("id", experiment.id)
                current = Experiment.from_dict(current_raw)
                experiment = self._merge_experiment(current, experiment)
            fd, tmp_name = tempfile.mkstemp(prefix=f"{experiment.id}-", suffix=".tmp", dir=str(self.dir))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    yaml.safe_dump(
                        experiment.model_dump(mode="json"),
                        handle,
                        default_flow_style=False,
                        allow_unicode=True,
                        sort_keys=False,
                    )
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp_name, path)
            finally:
                if os.path.exists(tmp_name):
                    os.unlink(tmp_name)
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
