"""Tests for Layer 2: forge/agent — strategist, trainer, data agent, loop."""

import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Trigger env registrations
import forge.env.game       # noqa: F401
import forge.env.navworld   # noqa: F401
import forge.env.swe        # noqa: F401
import forge.env.liveweb    # noqa: F401
import forge.env.lgc        # noqa: F401
import forge.env.print_env  # noqa: F401

from forge.agent.strategist import StrategistAgent, GapAnalysis
from forge.agent.trainer import TrainerAgent
from forge.agent.data_agent import DataAgent
from forge.agent.loop import EvolutionLoop, StepResult
from forge.pipeline.experiment import ExperimentTracker, Experiment
from forge.pipeline.eval import Evaluator, EvalReport


# ── StrategistAgent ──

class TestGapAnalysis:
    def test_analyze_finds_weakest(self):
        tracker = ExperimentTracker(tempfile.mkdtemp())
        agent = StrategistAgent(tracker)
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
        tracker = ExperimentTracker(tempfile.mkdtemp())
        agent = StrategistAgent(tracker)
        gap = agent.analyze_gap({"A": 4.0, "B": 9.0})
        # geo_mean(4, 9) = 6.0
        assert abs(gap.geo_mean - 6.0) < 0.01

    def test_analyze_empty_scores(self):
        tracker = ExperimentTracker(tempfile.mkdtemp())
        agent = StrategistAgent(tracker)
        gap = agent.analyze_gap({})
        assert gap.geo_mean == 0.0
        assert len(gap.recommendations) > 0

    def test_analyze_zero_score_recommendation(self):
        tracker = ExperimentTracker(tempfile.mkdtemp())
        agent = StrategistAgent(tracker)
        gap = agent.analyze_gap({"GAME": 50.0, "NAVWORLD": 0.0})
        assert any("CRITICAL" in r or "0" in r for r in gap.recommendations)

    def test_propose_experiment(self):
        tracker = ExperimentTracker(tempfile.mkdtemp())
        agent = StrategistAgent(tracker)
        gap = agent.analyze_gap({"GAME": 80.0, "NAVWORLD": 20.0})
        exp = agent.propose_experiment(gap)
        assert isinstance(exp, Experiment)
        assert "navworld" in exp.variable.lower()
        assert exp.hypothesis != ""


class TestStrategistMethodSwitch:
    def test_no_switch_insufficient_data(self):
        tracker = ExperimentTracker(tempfile.mkdtemp())
        agent = StrategistAgent(tracker)
        result = agent.should_switch_method("GAME")
        assert result is None


# ── TrainerAgent ──

class TestTrainerAgent:
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
    def _make_loop(self):
        tmpdir = tempfile.mkdtemp()
        tracker = ExperimentTracker(tmpdir)
        strategist = StrategistAgent(tracker)
        trainer = TrainerAgent()
        data_agent = DataAgent()
        return EvolutionLoop(strategist=strategist, trainer=trainer, data_agent=data_agent)

    def test_step_dry_run(self):
        loop = self._make_loop()
        gap = loop.strategist.analyze_gap({"GAME": 50.0, "NAVWORLD": 20.0})
        assert gap.weakest_env == "NAVWORLD"
        exp = loop.strategist.propose_experiment(gap)
        assert "navworld" in exp.variable.lower()

    def test_run_dry_run(self):
        """Test that gap analysis + experiment proposal works across steps."""
        loop = self._make_loop()
        scores = {"GAME": 50.0, "NAVWORLD": 20.0}
        gap1 = loop.strategist.analyze_gap(scores)
        gap2 = loop.strategist.analyze_gap(scores)
        assert gap1.weakest_env == gap2.weakest_env

    def test_step_result_dataclass(self):
        result = StepResult(
            step=1,
            gap=GapAnalysis(weakest_env="GAME", geo_mean=40.0),
            experiment_id="v1",
            eval_report=EvalReport(model_path="test"),
            improved=False,
        )
        s = result.summary()
        assert "Step 1" in s
        assert "GAME" in s
