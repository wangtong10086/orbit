"""Data agent — automated data preparation and quality management.

Implements the data side of the training loop:
- Prepare data for experiments
- Monitor data quality
- Trigger generation when data is insufficient
"""

from __future__ import annotations

from forge.foundation.environment_catalog import EnvironmentCatalog, default_environment_catalog
from forge.pipeline.data import DataPipeline
from forge.pipeline.experiment import Experiment


class DataAgent:
    """Automated data agent — prepares data for experiments.

    Usage:
        data_agent = DataAgent()
        data_agent.prepare(experiment)
    """

    def __init__(self, catalog: EnvironmentCatalog | None = None):
        self.catalog = catalog or default_environment_catalog()

    def prepare(self, experiment: Experiment) -> dict:
        """Prepare data for an experiment.

        1. Check what data exists for target environments
        2. Validate quality
        3. Generate more if needed
        4. Return data status report

        Returns:
            Status dict with env_name -> {count, quality, path}
        """
        status = {}
        for env_name, env_config in experiment.data_config.items():
            try:
                pipe = DataPipeline(env_name, catalog=self.catalog)
                status[env_name] = {
                    "ready": True,
                    "count": pipe.count,
                    "config": env_config,
                }
            except KeyError:
                status[env_name] = {
                    "ready": False,
                    "error": f"Unknown environment: {env_name}",
                }
        return status

    def audit(self, env_name: str, records: list[dict]) -> dict:
        """Run quality audit on records for an environment."""
        pipe = DataPipeline(env_name, catalog=self.catalog)
        report = pipe.ingest(records)
        return {
            "total": report.total,
            "accepted": report.accepted,
            "dropped": report.dropped,
            "invalid": report.invalid,
            "duplicate": report.duplicate,
            "acceptance_rate": report.accepted / max(report.total, 1),
        }

    def check_sufficiency(self, env_name: str, current_count: int) -> dict:
        """Check if current data is sufficient for training.

        Returns status and recommendations.
        """
        env = self.catalog.make_data(env_name)
        target = env.spec.task_count * 5  # Rough heuristic: 5x task count

        return {
            "env": env_name,
            "current": current_count,
            "target": target,
            "sufficient": current_count >= target,
            "deficit": max(0, target - current_count),
        }
