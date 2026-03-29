"""Evolution loop — orchestrates the full self-evolution cycle.

Composes Strategist + Trainer + Data agents into an automated loop:
  analyze gaps → design experiment → prepare data → train → evaluate → reflect

Corresponds to the "Agentic Crafting" concept from the ALE paper.
"""

from __future__ import annotations

from dataclasses import dataclass

from forge.control import ControlPlane
from forge.control.experiment import TrainingLifecycleState
from forge.agent.strategist import StrategistAgent, GapAnalysis
from forge.agent.trainer import TrainerAgent, TrainingOutcome
from forge.agent.data_agent import DataAgent
from forge.pipeline.eval import EvalReport


@dataclass
class StepResult:
    """Result of a single evolution step."""

    step: int
    status: str
    gap: GapAnalysis
    experiment_id: str
    eval_report: EvalReport | None
    improved: bool
    reason: str = ""
    training_outcome: TrainingOutcome | None = None

    def summary(self) -> str:
        geo_mean = self.eval_report.geo_mean if self.eval_report else 0.0
        return (
            f"Step {self.step}: "
            f"status={self.status}, "
            f"target={self.gap.weakest_env}, "
            f"geo_mean={geo_mean:.2f}, "
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
        control_plane: ControlPlane,
        strategist: StrategistAgent,
        trainer: TrainerAgent,
        data_agent: DataAgent,
    ):
        self.control_plane = control_plane
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

        if not current_scores:
            result = StepResult(
                step=self._step_count,
                status="blocked",
                gap=GapAnalysis(),
                experiment_id="",
                eval_report=None,
                improved=False,
                reason="No current scores available",
            )
            self._history.append(result)
            return result

        # 1. Analyze gaps
        gap = self.strategist.analyze_gap(current_scores)

        # 2. Propose experiment
        experiment = self.strategist.propose_experiment(gap)
        self.control_plane.save_experiment(experiment)

        # 3. Prepare data
        data_status = self.data_agent.prepare(experiment)
        if any(not info.get("ready", False) for info in data_status.values()):
            experiment.status = TrainingLifecycleState.BLOCKED
            experiment.results.extra["data_prepare"] = data_status
            self.control_plane.save_experiment(experiment)
            result = StepResult(
                step=self._step_count,
                status="blocked",
                gap=gap,
                experiment_id=experiment.id,
                eval_report=None,
                improved=False,
                reason="Required data preparation is not ready",
            )
            self._history.append(result)
            return result

        # 4. Execute through the trainer pipeline
        try:
            training_outcome = self.trainer.execute(experiment)
        except ValueError as exc:
            experiment.status = TrainingLifecycleState.BLOCKED
            experiment.results.extra["training_error"] = {"reason": str(exc)}
            self.control_plane.save_experiment(experiment)
            result = StepResult(
                step=self._step_count,
                status="blocked",
                gap=gap,
                experiment_id=experiment.id,
                eval_report=None,
                improved=False,
                reason=str(exc),
            )
            self._history.append(result)
            return result
        if training_outcome.status != "completed" or training_outcome.eval_report is None:
            persisted = self.control_plane.load_experiment(experiment.id)
            if persisted is not None:
                if training_outcome.status in {"completed", "failed", "terminated", "blocked", "running", "prepared", "draft"}:
                    persisted.status = TrainingLifecycleState(training_outcome.status)
                if training_outcome.reason:
                    persisted.results.extra["training_error"] = {"reason": training_outcome.reason}
                self.control_plane.save_experiment(persisted)
            result = StepResult(
                step=self._step_count,
                status=training_outcome.status,
                gap=gap,
                experiment_id=experiment.id,
                eval_report=None,
                improved=False,
                reason=training_outcome.reason,
                training_outcome=training_outcome,
            )
            self._history.append(result)
            return result

        # 5. Check improvement
        report = training_outcome.eval_report
        improved = report.geo_mean > gap.geo_mean if gap.geo_mean > 0 else True

        result = StepResult(
            step=self._step_count,
            status="completed",
            gap=gap,
            experiment_id=experiment.id,
            eval_report=report,
            improved=improved,
            training_outcome=training_outcome,
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
                      Required; dry-run fake-success paths are not allowed.
        """
        if score_fn is None:
            raise ValueError("score_fn is required for EvolutionLoop.run")

        results = []
        for i in range(max_steps):
            scores = score_fn()
            result = self.step(scores)
            results.append(result)

            if result.status != "completed":
                break

            if result.eval_report and result.eval_report.geo_mean >= target_geo_mean:
                print(f"Target geo mean {target_geo_mean} achieved at step {i+1}")
                break

        return results

    @property
    def history(self) -> list[StepResult]:
        return list(self._history)
