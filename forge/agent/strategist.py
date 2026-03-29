"""Strategist agent — automated experiment design and gap analysis.

Implements the "think" part of the training loop:
- Analyze leaderboard gaps
- Propose experiments (one variable at a time)
- Decide when to switch methods (SFT → DPO)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from forge.control.experiment import Experiment, ExperimentStore
from forge.foundation.scoring import ScoringPolicy


@dataclass
class GapAnalysis:
    """Quantitative analysis of current position vs competition."""

    weakest_env: str = ""
    weakest_score: float = 0.0
    strongest_env: str = ""
    strongest_score: float = 0.0
    geo_mean: float = 0.0
    rank: int = 0
    env_scores: dict[str, float] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)


class StrategistAgent:
    """Automated strategy agent — designs experiments based on gap analysis.

    Usage:
        strategist = StrategistAgent(ExperimentStore("experiments/"))
        gap = strategist.analyze_gap(current_scores)
        experiment = strategist.propose_experiment(gap)
    """

    def __init__(self, experiments: ExperimentStore):
        self.experiments = experiments

    def analyze_gap(self, env_scores: dict[str, float]) -> GapAnalysis:
        """Analyze current scores to find the weakest link.

        The leaderboard uses geometric mean, so the weakest env
        dominates the overall score. Focus there.
        """
        gap = GapAnalysis(env_scores=env_scores)

        if not env_scores:
            gap.recommendations.append("No scores available — run evaluation first")
            return gap

        # Find weakest and strongest
        sorted_envs = sorted(env_scores.items(), key=lambda x: x[1])
        gap.weakest_env, gap.weakest_score = sorted_envs[0]
        gap.strongest_env, gap.strongest_score = sorted_envs[-1]

        # Geometric mean
        gap.geo_mean = ScoringPolicy.strict_geo_mean(env_scores.values())

        # Recommendations
        if gap.weakest_score == 0:
            gap.recommendations.append(
                f"CRITICAL: {gap.weakest_env} at 0% — structural zero kills geo mean"
            )
        elif gap.weakest_score < gap.geo_mean * 0.5:
            gap.recommendations.append(
                f"FOCUS: {gap.weakest_env} ({gap.weakest_score:.1f}) dragging down geo mean"
            )

        return gap

    def propose_experiment(self, gap: GapAnalysis) -> Experiment:
        """Propose the next experiment based on gap analysis.

        Rules:
        1. Target weakest environment
        2. One variable per experiment
        3. Check if method switch needed
        """
        exp = Experiment(
            id=self._next_experiment_id(),
            variable=f"improve_{gap.weakest_env.lower()}_data",
            hypothesis=(
                f"Adding more high-quality {gap.weakest_env} data should improve "
                f"score from {gap.weakest_score:.1f} closer to the geo mean ({gap.geo_mean:.1f})"
            ),
        )
        return exp

    def should_switch_method(self, env: str) -> str | None:
        """Check if SFT is plateauing for this env.

        Triggers:
        - 2x data yields <15% improvement → escalate to DPO
        - Score at 0% across 3+ versions → flag as unlearnable
        """
        completed = self.experiments.list_experiments(status="completed")
        env_results = [
            e for e in completed
            if env.lower() in e.variable.lower()
        ]

        if len(env_results) >= 3:
            # Check for plateau
            recent_scores = []
            for e in env_results[-3:]:
                score = e.results.get(env, {}).get("score", 0)
                recent_scores.append(score)

            if all(s == 0 for s in recent_scores):
                return "flag_unlearnable"

            if len(recent_scores) >= 2:
                improvement = recent_scores[-1] - recent_scores[-2]
                if abs(improvement) < 0.15 * recent_scores[-2] if recent_scores[-2] > 0 else False:
                    return "dpo"

        return None

    def _next_experiment_id(self) -> str:
        """Generate next experiment ID based on existing experiments."""
        return self.experiments.next_experiment_id()
