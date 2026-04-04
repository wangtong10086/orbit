"""Tests for Layer 2: forge/agent — strategist, trainer, data agent, loop."""

import asyncio
import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forge.core.control.service import CoreControlService
from forge.core.templates.registry import ExecutionTemplateRegistry
from forge.core.experiments import Experiment, ExperimentStore
from forge.core.execution.bundle import JobBundle
from forge.foundation.contracts import TrainingSpec
from forge.core.contracts.execution import CollectArtifactsRequest, ExecutionRequest, RunHandle, RunLogsRequest, RunStatusRequest, TerminateRunRequest
from forge.tasks import build_default_task_registry
from forge.agent.strategist import StrategistAgent, GapAnalysis
from forge.agent.trainer import TrainerAgent, TrainingOutcome
from forge.agent.data_agent import DataAgent
from forge.agent.loop import EvolutionLoop, StepResult
from forge.pipeline.eval import EvaluationPipeline, EvalReport
from tests.eval_helpers import make_script_runner


class _FakeRuntimeBackend:
    async def run(self, request: ExecutionRequest) -> RunHandle:
        bundle = JobBundle(request.bundle_path)
        job = bundle.load_job()
        return RunHandle(runtime_kind="fake", run_id=f"launch-{job.job_id}", target_id="fake-target", bundle_path=str(bundle.path))

    async def status(self, request: RunStatusRequest):
        raise NotImplementedError

    async def logs(self, request: RunLogsRequest):
        raise NotImplementedError

    async def collect(self, request: CollectArtifactsRequest):
        raise NotImplementedError

    async def terminate(self, request: TerminateRunRequest):
        raise NotImplementedError


# ── StrategistAgent ──

class TestGapAnalysis:
    def test_analyze_finds_weakest(self):
        experiments = ExperimentStore(tempfile.mkdtemp())
        agent = StrategistAgent(experiments)
        gap = agent.analyze_gap({
            "GAME": 80.0,
            "NAVWORLD": 30.0,
            "SWE": 60.0,
        })
        assert gap.weakest_env == "NAVWORLD"
        assert gap.weakest_score == 30.0
        assert gap.strongest_env == "GAME"
        assert gap.strongest_score == 80.0

    def test_analyze_geo_mean(self):
        experiments = ExperimentStore(tempfile.mkdtemp())
        agent = StrategistAgent(experiments)
        gap = agent.analyze_gap({"A": 4.0, "B": 9.0})
        # geo_mean(4, 9) = 6.0
        assert abs(gap.geo_mean - 6.0) < 0.01

    def test_analyze_empty_scores(self):
        experiments = ExperimentStore(tempfile.mkdtemp())
        agent = StrategistAgent(experiments)
        gap = agent.analyze_gap({})
        assert gap.geo_mean == 0.0
        assert len(gap.recommendations) > 0

    def test_analyze_zero_score_recommendation(self):
        experiments = ExperimentStore(tempfile.mkdtemp())
        agent = StrategistAgent(experiments)
        gap = agent.analyze_gap({"GAME": 50.0, "NAVWORLD": 0.0})
        assert gap.geo_mean == 0.0
        assert any("CRITICAL" in r or "0" in r for r in gap.recommendations)

    def test_propose_experiment(self):
        experiments = ExperimentStore(tempfile.mkdtemp())
        agent = StrategistAgent(experiments)
        gap = agent.analyze_gap({"GAME": 80.0, "NAVWORLD": 20.0})
        exp = agent.propose_experiment(gap)
        assert isinstance(exp, Experiment)
        assert "navworld" in exp.variable.lower()
        assert exp.hypothesis != ""


class TestStrategistMethodSwitch:
    def test_no_switch_insufficient_data(self):
        experiments = ExperimentStore(tempfile.mkdtemp())
        agent = StrategistAgent(experiments)
        result = agent.should_switch_method("GAME")
        assert result is None


# ── TrainerAgent ──

class TestTrainerAgent:
    def test_build_training_spec(self):
        agent = TrainerAgent()
        exp = Experiment(
            id="t0",
            variable="test",
            hypothesis="test",
            train_config={
                "model": "Qwen/Qwen3-32B",
                "learning_rate": 1e-4,
                "lora_rank": 64,
                "max_length": 4096,
                "num_train_epochs": 1,
                "output_dir": "/tmp/checkpoints",
            },
            data_config={"GAME": {"count": 100}, "NAVWORLD": {"count": 50}},
        )
        spec = agent.build_training_spec(exp, dataset_path="/tmp/data.jsonl")
        assert isinstance(spec, TrainingSpec)
        assert spec.experiment_id == "t0"
        assert spec.dataset_path == "/tmp/data.jsonl"
        assert spec.environments == ("GAME", "NAVWORLD")
        assert spec.output_dir == "/tmp/checkpoints"

    def test_validate_no_config(self):
        agent = TrainerAgent()
        exp = Experiment(id="t1", variable="test", hypothesis="test")
        issues = agent.validate_experiment(exp)
        assert len(issues) > 0
        assert any("train_config" in i for i in issues)

    def test_validate_valid_config(self):
        agent = TrainerAgent()
        exp = Experiment(
            id="t2", variable="test", hypothesis="test",
            train_config={
                "learning_rate": 1e-4,
                "lora_rank": 64,
                "max_length": 4096,
                "num_train_epochs": 1,
            },
            data_config={"GAME": {"count": 100}},
        )
        issues = agent.validate_experiment(exp)
        assert issues == [], f"Unexpected issues: {issues}"

    def test_validate_bad_lr(self):
        agent = TrainerAgent()
        exp = Experiment(
            id="t3", variable="test", hypothesis="test",
            train_config={"learning_rate": -1},
            data_config={"GAME": 100},
        )
        issues = agent.validate_experiment(exp)
        assert any("learning_rate" in i for i in issues)

    def test_execute_invalid_raises(self):
        agent = TrainerAgent()
        exp = Experiment(id="t4", variable="test", hypothesis="test")
        try:
            agent.execute(exp)
            assert False, "Should raise ValueError"
        except ValueError as e:
            assert "validation failed" in str(e).lower()

    def test_execute_blocks_without_provider(self):
        agent = TrainerAgent(evaluator=EvaluationPipeline(runner=make_script_runner(Path("/tmp"), {"GAME": [0.5]})))
        exp = Experiment(
            id="t4b",
            variable="test",
            hypothesis="test",
            train_config={
                "learning_rate": 1e-4,
                "lora_rank": 64,
                "max_length": 4096,
                "num_train_epochs": 1,
                "output_dir": "/tmp/checkpoints",
            },
            data_config={"GAME": {"count": 100}},
        )
        outcome = agent.execute(exp)
        assert outcome.status == "blocked"
        assert "execution template" in outcome.reason.lower()

    def test_execute_uses_evaluation_contract(self, tmp_path):
        dataset_path = tmp_path / "train.jsonl"
        dataset_path.write_text('{"messages":[]}\n')
        control_plane = CoreControlService(
            experiments=ExperimentStore(str(tmp_path / "experiments")),
            execution=_FakeRuntimeBackend(),
            templates=ExecutionTemplateRegistry(),
            task_registry=build_default_task_registry(),
        )
        agent = TrainerAgent(
            control_plane=control_plane,
            evaluator=EvaluationPipeline(runner=make_script_runner(tmp_path, {"GAME": [0.5]})),
            dataset_path_resolver=lambda exp: str(dataset_path),
            template_id_resolver=lambda exp: "local-host",
            model_path_resolver=lambda exp, launch: f"/tmp/checkpoints/{exp.id}",
        )
        exp = Experiment(
            id="t5",
            variable="test",
            hypothesis="test",
            train_config={
                "learning_rate": 1e-4,
                "lora_rank": 64,
                "max_length": 4096,
                "num_train_epochs": 1,
                "output_dir": "/tmp/checkpoints",
            },
            data_config={"GAME": {"count": 100}},
        )
        outcome = agent.execute(exp)
        assert outcome.status == "completed"
        assert outcome.eval_report is not None
        assert outcome.eval_report.model_path == "/tmp/checkpoints/t5"
        assert "GAME" in outcome.eval_report.results
        persisted = control_plane.load_experiment("t5")
        assert persisted is not None
        assert persisted.status.value == "completed"
        assert persisted.results.training_run is not None
        assert persisted.results.training_run.run_id == "launch-t5"
        assert persisted.results.agent_eval is not None
        assert persisted.results.agent_eval.model_path == "/tmp/checkpoints/t5"

    def test_execute_can_launch_without_fake_completion(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as handle:
            handle.write('{"messages":[]}\n')
            dataset_path = handle.name
        control_plane = CoreControlService(
            experiments=ExperimentStore(tempfile.mkdtemp()),
            execution=_FakeRuntimeBackend(),
            templates=ExecutionTemplateRegistry(),
            task_registry=build_default_task_registry(),
        )
        agent = TrainerAgent(
            control_plane=control_plane,
            dataset_path_resolver=lambda exp: dataset_path,
            template_id_resolver=lambda exp: "local-host",
        )
        exp = Experiment(
            id="t6",
            variable="test",
            hypothesis="test",
            train_config={
                "learning_rate": 1e-4,
                "lora_rank": 64,
                "max_length": 4096,
                "num_train_epochs": 1,
                "output_dir": "/tmp/checkpoints",
            },
            data_config={"GAME": {"count": 100}},
        )
        outcome = agent.execute(exp)
        assert outcome.status == "launched"
        assert outcome.launch is not None
        assert outcome.eval_report is None
        persisted = control_plane.load_experiment("t6")
        assert persisted is not None
        assert persisted.status.value == "running"
        assert persisted.results.training_run is not None
        assert persisted.results.training_run.run_id == "launch-t6"


# ── DataAgent ──

class TestDataAgent:
    def test_audit_game(self):
        agent = DataAgent()
        records = [
            {
                "messages": [
                    {"role": "system", "content": "Game player."},
                    {"role": "user", "content": "Play chess"},
                    {"role": "assistant", "content": "I play e4."},
                ],
                "env": "GAME",
                "score": 0.5,
            },
            {
                "messages": [{"role": "user", "content": "hi"}],
                "env": "GAME",
            },
        ]
        result = agent.audit("GAME", records)
        assert result["total"] == 2
        assert result["accepted"] == 1

    def test_check_sufficiency(self):
        agent = DataAgent()
        result = agent.check_sufficiency("GAME", current_count=1000)
        assert "sufficient" in result
        assert "target" in result
        assert "deficit" in result

    def test_prepare_unknown_env(self):
        agent = DataAgent()
        exp = Experiment(
            id="d1", variable="test", hypothesis="test",
            data_config={"NONEXISTENT": {"count": 50}},
        )
        status = agent.prepare(exp)
        assert "NONEXISTENT" in status
        assert status["NONEXISTENT"]["ready"] is False


# ── EvolutionLoop ──

class TestEvolutionLoop:
    def _make_loop(self, trainer=None, strategist=None):
        tmpdir = tempfile.mkdtemp()
        experiments = ExperimentStore(tmpdir)
        control_plane = CoreControlService(
            experiments=experiments,
            execution=_FakeRuntimeBackend(),
            templates=ExecutionTemplateRegistry(),
            task_registry=build_default_task_registry(),
        )
        strategist = strategist or StrategistAgent(experiments)
        trainer = trainer or TrainerAgent(control_plane=control_plane)
        data_agent = DataAgent()
        return EvolutionLoop(control_plane=control_plane, strategist=strategist, trainer=trainer, data_agent=data_agent)

    def test_step_blocks_without_scores(self):
        loop = self._make_loop()
        result = loop.step({})
        assert result.status == "blocked"
        assert "scores" in result.reason.lower()

    def test_run_requires_score_fn(self):
        loop = self._make_loop()
        try:
            loop.run()
            assert False, "Should raise"
        except ValueError as exc:
            assert "score_fn" in str(exc)

    def test_run_stops_on_blocked_training(self):
        loop = self._make_loop(trainer=TrainerAgent())
        results = loop.run(max_steps=3, score_fn=lambda: {"GAME": 50.0, "NAVWORLD": 20.0})
        assert len(results) == 1
        assert results[0].status == "blocked"

    def test_run_completed_with_real_outcome(self, tmp_path):
        class _ConfiguredStrategist(StrategistAgent):
            def __init__(self):
                super().__init__(ExperimentStore(tempfile.mkdtemp()))

            def propose_experiment(self, gap: GapAnalysis) -> Experiment:
                return Experiment(
                    id="v1",
                    variable="improve_navworld_data",
                    hypothesis="test",
                    train_config={
                        "learning_rate": 1e-4,
                        "lora_rank": 64,
                        "max_length": 4096,
                        "num_train_epochs": 1,
                        "output_dir": "/tmp/checkpoints",
                    },
                    data_config={"GAME": {"count": 100}, "NAVWORLD": {"count": 100}},
                )

        control_plane = CoreControlService(
            experiments=ExperimentStore(tempfile.mkdtemp()),
            execution=_FakeRuntimeBackend(),
            templates=ExecutionTemplateRegistry(),
            task_registry=build_default_task_registry(),
        )
        trainer = TrainerAgent(
            control_plane=control_plane,
            evaluator=EvaluationPipeline(runner=make_script_runner(tmp_path, {"NAVWORLD": [0.4], "GAME": [0.7]})),
            dataset_path_resolver=lambda exp: str(tmp_path / "train.jsonl"),
            template_id_resolver=lambda exp: "local-host",
            model_path_resolver=lambda exp, launch: f"/tmp/checkpoints/{exp.id}",
        )
        (tmp_path / "train.jsonl").write_text('{"messages":[]}\n')
        loop = self._make_loop(trainer=trainer, strategist=_ConfiguredStrategist())
        results = loop.run(max_steps=1, score_fn=lambda: {"GAME": 50.0, "NAVWORLD": 20.0})
        assert len(results) == 1
        assert results[0].status == "completed"
        assert results[0].eval_report is not None

    def test_step_result_dataclass(self):
        result = StepResult(
            step=1,
            status="completed",
            gap=GapAnalysis(weakest_env="GAME", geo_mean=40.0),
            experiment_id="v1",
            eval_report=EvalReport(model_path="test"),
            improved=False,
        )
        s = result.summary()
        assert "Step 1" in s
        assert "GAME" in s
