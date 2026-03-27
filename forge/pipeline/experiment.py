"""Experiment tracker — manage experiment lifecycle via YAML files.

Wraps the existing experiments/*.yaml workflow with a programmatic interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class Experiment:
    """A single experiment definition."""

    id: str
    variable: str
    hypothesis: str
    status: str = "draft"  # draft → approved → running → completed → failed
    train_config: dict = field(default_factory=dict)
    data_config: dict = field(default_factory=dict)
    results: dict = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "variable": self.variable,
            "hypothesis": self.hypothesis,
            "status": self.status,
            "train_config": self.train_config,
            "data_config": self.data_config,
            "results": self.results,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Experiment":
        return cls(
            id=d.get("id", ""),
            variable=d.get("variable", ""),
            hypothesis=d.get("hypothesis", ""),
            status=d.get("status", "draft"),
            train_config=d.get("train_config", {}),
            data_config=d.get("data_config", {}),
            results=d.get("results", {}),
            notes=d.get("notes", ""),
        )


class ExperimentTracker:
    """Track experiments via YAML files in experiments/ directory.

    Usage:
        tracker = ExperimentTracker("experiments/")
        exp = tracker.load("v2.25")
        tracker.update_status(exp.id, "running")
    """

    def __init__(self, experiments_dir: str = "experiments"):
        self.dir = Path(experiments_dir)

    def load(self, exp_id: str) -> Optional[Experiment]:
        """Load an experiment from its YAML file."""
        # Try various naming patterns
        for pattern in [f"{exp_id}.yaml", f"{exp_id}-draft.yaml", f"{exp_id}-ab.yaml"]:
            path = self.dir / pattern
            if path.exists():
                with open(path) as f:
                    data = yaml.safe_load(f)
                if data:
                    data.setdefault("id", exp_id)
                    return Experiment.from_dict(data)
        return None

    def save(self, exp: Experiment) -> Path:
        """Save experiment to YAML file."""
        path = self.dir / f"{exp.id}.yaml"
        with open(path, "w") as f:
            yaml.safe_dump(exp.to_dict(), f, default_flow_style=False, allow_unicode=True)
        return path

    def list_experiments(self, status: Optional[str] = None) -> list[Experiment]:
        """List all experiments, optionally filtered by status."""
        experiments = []
        for path in sorted(self.dir.glob("*.yaml")):
            try:
                with open(path) as f:
                    data = yaml.safe_load(f)
                if data:
                    data.setdefault("id", path.stem)
                    exp = Experiment.from_dict(data)
                    if status is None or exp.status == status:
                        experiments.append(exp)
            except Exception:
                continue
        return experiments

    def update_status(self, exp_id: str, status: str) -> bool:
        """Update an experiment's status."""
        exp = self.load(exp_id)
        if exp is None:
            return False
        exp.status = status
        self.save(exp)
        return True
