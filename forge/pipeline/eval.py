"""Evaluation pipeline across environments.

Orchestrates model evaluation against all environments,
computing per-env scores and geometric mean rank.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from forge.foundation.contracts import EvaluationRunner, EvaluationSpec
from forge.foundation.environment_catalog import EnvironmentCatalog, default_environment_catalog
from forge.foundation.evaluation import ScriptEvaluationRunner
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


class EvaluationPipeline(EvaluationRunner):
    """Real evaluation pipeline over an executable evaluation runner.

    Usage:
        pipeline = EvaluationPipeline(envs=["GAME", "NAVWORLD"])
        report = pipeline.run(model_path="path/to/model", samples=100)
    """

    def __init__(
        self,
        envs: list[str] | None = None,
        catalog: EnvironmentCatalog | None = None,
        runner: EvaluationRunner | None = None,
    ):
        self.catalog = catalog or default_environment_catalog()
        self.env_names = envs or self.catalog.list_data_envs()
        self.runner = runner or ScriptEvaluationRunner()

    def run(
        self,
        model_path: str,
        samples_per_env: int = 100,
        base_url: str = "http://172.17.0.1:30000/v1",
        output_dir: str = "",
        concurrency: int = 5,
        seed: int = 42,
        affinetes_dir: str = "/root/affinetes",
        api_key: str = "",
        skip_build: bool = False,
    ) -> EvalReport:
        """Run evaluation across all configured environments."""
        spec = EvaluationSpec(
            model_path=model_path,
            environments=tuple(self.env_names),
            samples_per_env=samples_per_env,
            base_url=base_url,
            output_dir=output_dir,
            concurrency=concurrency,
            seed=seed,
            affinetes_dir=affinetes_dir,
            api_key=api_key,
            skip_build=skip_build,
        )
        return self.run_evaluation(spec)

    def run_evaluation(self, spec: EvaluationSpec) -> EvalReport:
        """Run evaluation from the stable foundation contract using the real runner."""
        for env_name in spec.environments:
            self.catalog.make_data(env_name)

        raw = self.runner.run_evaluation(spec)
        output_dir = Path(raw["output_dir"])

        report = EvalReport(model_path=spec.model_path)
        for env_name in spec.environments:
            env_file = output_dir / f"eval_{env_name.lower().replace('-', '_')}.json"
            if not env_file.exists():
                raise FileNotFoundError(f"Evaluation artifact not found for {env_name}: {env_file}")
            env_summary = json.loads(env_file.read_text())
            scores = [float(result.get("score", 0.0)) * 100.0 for result in env_summary.get("results", [])]
            task_ids = [str(result.get("task_id", "")) for result in env_summary.get("results", [])]
            report.results[env_name] = EnvResult(
                env_name=env_name,
                mean_score=float(env_summary.get("mean_score", 0.0)) * 100.0,
                scores=scores,
                task_ids=task_ids,
                sample_count=int(env_summary.get("samples", 0)),
                completeness=(
                    float(env_summary.get("valid_count", 0)) / float(env_summary.get("samples", 1))
                    if env_summary.get("samples", 0)
                    else 0.0
                ),
            )
        return report
