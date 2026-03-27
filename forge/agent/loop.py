"""Evolution loop — orchestrates the full self-evolution cycle.

Composes Strategist + Trainer + Data agents into an automated loop:
  analyze gaps → design experiment → prepare data → train → evaluate → reflect

Corresponds to the "Agentic Crafting" concept from the ALE paper.
"""

from __future__ import annotations

from dataclasses import dataclass

from forge.agent.strategist import StrategistAgent, GapAnalysis
from forge.agent.trainer import TrainerAgent
from forge.agent.data_agent import DataAgent
from forge.pipeline.eval import EvalReport


@dataclass
class StepResult:
    """Result of a single evolution step."""

    step: int
    gap: GapAnalysis
    experiment_id: str
    eval_report: EvalReport
    improved: bool

    def summary(self) -> str:
        return (
            f"Step {self.step}: "
            f"target={self.gap.weakest_env}, "
            f"geo_mean={self.eval_report.geo_mean:.2f}, "
            f"improved={self.improved}"
        )


class EvolutionLoop:
    """Full self-evolution loop — the top-level orchestrator.

    Usage:
        loop = EvolutionLoop(
            strategist=StrategistAgent(tracker),
            trainer=TrainerAgent(evaluator),
            data_agent=DataAgent(),
        )
        results = loop.run(max_steps=5)
    """

    def __init__(
        self,
        strategist: StrategistAgent,
        trainer: TrainerAgent,
        data_agent: DataAgent,
    ):
        self.strategist = strategist
        self.trainer = trainer
        self.data_agent = data_agent
        self._step_count = 0
        self._history: list[StepResult] = []

    def step(self, current_scores: dict[str, float]) -> StepResult:
        """Execute one evolution step.

        1. Analyze gaps (strategist)
        2. Propose experiment (strategist)
        3. Prepare data (data agent)
        4. Execute training + eval (trainer)
        5. Record results and reflect
        """
        self._step_count += 1

        # 1. Analyze gaps
        gap = self.strategist.analyze_gap(current_scores)

        # 2. Propose experiment
        experiment = self.strategist.propose_experiment(gap)

        # 3. Prepare data
        self.data_agent.prepare(experiment)

        # 4. Execute (placeholder — actual training requires GPU resources)
        report = self.trainer.execute(experiment)

        # 5. Check improvement
        improved = report.geo_mean > gap.geo_mean if gap.geo_mean > 0 else True

        result = StepResult(
            step=self._step_count,
            gap=gap,
            experiment_id=experiment.id,
            eval_report=report,
            improved=improved,
        )
        self._history.append(result)
        return result

    def run(self, max_steps: int = 10, target_geo_mean: float = 100.0,
            score_fn=None) -> list[StepResult]:
        """Run multiple evolution steps.

        Args:
            max_steps: Maximum steps to run
            target_geo_mean: Stop when this geo mean is achieved
            score_fn: Callable that returns current env scores dict.
                      If None, uses empty scores (dry run).
        """
        results = []
        for i in range(max_steps):
            scores = score_fn() if score_fn else {}
            result = self.step(scores)
            results.append(result)

            if result.eval_report.geo_mean >= target_geo_mean:
                print(f"Target geo mean {target_geo_mean} achieved at step {i+1}")
                break

        return results

    @property
    def history(self) -> list[StepResult]:
        return list(self._history)
