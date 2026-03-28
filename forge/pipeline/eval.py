"""Evaluator — unified evaluation pipeline across environments.

Orchestrates model evaluation against all environments,
computing per-env scores and geometric mean rank.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from forge.foundation.environment_catalog import EnvironmentCatalog, default_environment_catalog
from forge.foundation.scoring import ScoringPolicy


@dataclass
class EnvResult:
    """Results for a single environment."""

    env_name: str
    mean_score: float = 0.0
    scores: list[float] = field(default_factory=list)
    task_ids: list[str] = field(default_factory=list)
    sample_count: int = 0
    completeness: float = 0.0


@dataclass
class EvalReport:
    """Full evaluation report across environments."""

    results: dict[str, EnvResult] = field(default_factory=dict)
    model_path: str = ""

    @property
    def env_names(self) -> list[str]:
        return list(self.results.keys())

    @property
    def geo_mean(self) -> float:
        """Geometric mean of per-env scores (leaderboard metric)."""
        return ScoringPolicy.strict_geo_mean(
            r.mean_score for r in self.results.values()
        )

    def summary(self) -> str:
        lines = [f"Model: {self.model_path}", f"Geo mean: {self.geo_mean:.2f}", ""]
        for name, result in sorted(self.results.items()):
            lines.append(
                f"  {name}: {result.mean_score:.2f} "
                f"(n={result.sample_count}, completeness={result.completeness:.1%})"
            )
        return "\n".join(lines)


class Evaluator:
    """Run model evaluation across environments.

    Usage:
        evaluator = Evaluator(envs=["GAME", "NAVWORLD"])
        report = evaluator.run(model_path="path/to/model", samples=100)
    """

    def __init__(
        self,
        envs: list[str] | None = None,
        catalog: EnvironmentCatalog | None = None,
    ):
        self.catalog = catalog or default_environment_catalog()
        self.env_names = envs or self.catalog.list_data_envs()

    def run(self, model_path: str, samples_per_env: int = 100) -> EvalReport:
        """Run evaluation across all configured environments.

        Note: This is a structured interface. Actual inference requires
        a running model endpoint (sglang), which is handled by
        scripts/eval_envs.py. This class provides the orchestration layer.
        """
        report = EvalReport(model_path=model_path)
        for env_name in self.env_names:
            self.catalog.make_data(env_name)
            report.results[env_name] = EnvResult(
                env_name=env_name,
                sample_count=samples_per_env,
            )
        return report
