"""Data agent — automated data preparation and quality management.

Implements the data side of the training loop:
- Prepare data for experiments
- Monitor data quality
- Trigger generation when data is insufficient
"""

from __future__ import annotations

from forge.core.experiments import Experiment
from forge.foundation.environment_catalog import EnvironmentCatalog, default_environment_catalog
from forge.foundation.repository import LocalCanonicalRepository, canonical_fingerprint


class DataAgent:
    """Automated data agent — prepares data for experiments.

    Usage:
        data_agent = DataAgent()
        data_agent.prepare(experiment)
    """

    def __init__(self, catalog: EnvironmentCatalog | None = None):
        self.catalog = catalog or default_environment_catalog()
        self.repository = LocalCanonicalRepository()

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
                self.catalog.make_data(env_name)
                path = self.repository.path_for(env_name)
                count = len(self.repository.load(env_name))
                status[env_name] = {
                    "ready": True,
                    "count": count,
                    "path": str(path),
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
        env = self.catalog.make_data(env_name)
        seen_fingerprints: set[str] = set()
        accepted = 0
        dropped = 0
        invalid = 0
        duplicate = 0

        for record in records:
            cleaned = env.clean_entry(dict(record))
            if cleaned is None:
                dropped += 1
                continue

            if env.validate_entry(cleaned):
                invalid += 1
                continue

            fingerprint = canonical_fingerprint(cleaned)
            if fingerprint in seen_fingerprints:
                duplicate += 1
                continue

            seen_fingerprints.add(fingerprint)
            accepted += 1

        total = accepted + dropped + invalid + duplicate
        return {
            "total": total,
            "accepted": accepted,
            "dropped": dropped,
            "invalid": invalid,
            "duplicate": duplicate,
            "acceptance_rate": accepted / max(total, 1),
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
