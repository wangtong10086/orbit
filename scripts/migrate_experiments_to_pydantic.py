"""Rewrite experiment YAML files into the active Pydantic schema."""

from __future__ import annotations

from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orbit.control.experiment import Experiment


def migrate_experiments(experiments_dir: str = "experiments") -> int:
    root = Path(experiments_dir)
    count = 0
    for path in sorted(root.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        raw.setdefault("id", path.stem)
        experiment = Experiment.from_dict(raw)
        path.write_text(
            yaml.safe_dump(
                experiment.model_dump(mode="json"),
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        count += 1
    return count


if __name__ == "__main__":
    rewritten = migrate_experiments()
    print(f"migrated {rewritten} experiment files")
