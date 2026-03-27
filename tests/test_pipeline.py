"""Tests for Layer 1: forge/pipeline — data, eval, experiment."""

import sys
import os
import tempfile
import math

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Trigger env registrations
import forge.env.game       # noqa: F401
import forge.env.navworld   # noqa: F401
import forge.env.swe        # noqa: F401
import forge.env.liveweb    # noqa: F401
import forge.env.lgc        # noqa: F401
import forge.env.print_env  # noqa: F401

from forge.pipeline.data import DataPipeline, IngestReport
from forge.pipeline.eval import Evaluator, EvalReport, EnvResult
from forge.pipeline.experiment import ExperimentTracker, Experiment


# ── DataPipeline ──

class TestIngestReport:
    def test_total(self):
        r = IngestReport(accepted=3, dropped=1, invalid=1, duplicate=1)
        assert r.total == 6

    def test_summary(self):
        r = IngestReport(accepted=5, dropped=2, invalid=1, duplicate=0)
        s = r.summary()
        assert "5/8" in s


class TestDataPipeline:
    def _game_record(self, content="I play e4."):
        return {
            "messages": [
                {"role": "system", "content": "You are a game player."},
                {"role": "user", "content": "Play chess"},
                {"role": "assistant", "content": content},
            ],
            "env": "GAME",
            "score": 0.5,
        }

    def test_ingest_valid(self):
        pipe = DataPipeline("GAME")
        report = pipe.ingest([self._game_record()])
        assert report.accepted == 1
        assert report.dropped == 0
        assert pipe.count == 1

    def test_ingest_invalid_dropped(self):
        pipe = DataPipeline("GAME")
        bad_record = {"messages": [{"role": "user", "content": "hi"}], "env": "GAME"}
        report = pipe.ingest([bad_record])
        assert report.accepted == 0
        assert pipe.count == 0

    def test_ingest_dedup(self):
        pipe = DataPipeline("GAME")
        rec = self._game_record()
        report = pipe.ingest([rec, rec])
        assert report.accepted == 1
        assert report.duplicate == 1
        assert pipe.count == 1

    def test_ingest_different_records(self):
        pipe = DataPipeline("GAME")
        r1 = self._game_record("I play e4.")
        r2 = self._game_record("I play d4.")
        report = pipe.ingest([r1, r2])
        assert report.accepted == 2
        assert pipe.count == 2

    def test_export(self):
        pipe = DataPipeline("GAME")
        pipe.ingest([self._game_record()])

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
            path = f.name

        try:
            count = pipe.export(path)
            assert count == 1
            import json
            with open(path) as f:
                lines = f.readlines()
            assert len(lines) == 1
            data = json.loads(lines[0])
            assert "messages" in data
        finally:
            os.unlink(path)

    def test_clear(self):
        pipe = DataPipeline("GAME")
        pipe.ingest([self._game_record()])
        assert pipe.count == 1
        pipe.clear()
        assert pipe.count == 0

    def test_unknown_env_raises(self):
        try:
            DataPipeline("NONEXISTENT")
            assert False, "Should raise KeyError"
        except KeyError:
            pass


# ── EvalReport ──

class TestEvalReport:
    def test_geo_mean_basic(self):
        report = EvalReport()
        report.results = {
            "A": EnvResult(env_name="A", mean_score=4.0),
            "B": EnvResult(env_name="B", mean_score=9.0),
        }
        # geo_mean(4, 9) = sqrt(36) = 6.0
        assert abs(report.geo_mean - 6.0) < 0.01

    def test_geo_mean_single(self):
        report = EvalReport()
        report.results = {"X": EnvResult(env_name="X", mean_score=25.0)}
        assert abs(report.geo_mean - 25.0) < 0.01

    def test_geo_mean_empty(self):
        report = EvalReport()
        assert report.geo_mean == 0.0

    def test_geo_mean_with_zero_score(self):
        report = EvalReport()
        report.results = {
            "A": EnvResult(env_name="A", mean_score=10.0),
            "B": EnvResult(env_name="B", mean_score=0.0),
        }
        # Zero score is excluded from geo mean
        assert abs(report.geo_mean - 10.0) < 0.01

    def test_summary(self):
        report = EvalReport(model_path="test_model")
        report.results = {"GAME": EnvResult(env_name="GAME", mean_score=50.0, sample_count=100)}
        s = report.summary()
        assert "test_model" in s
        assert "GAME" in s


class TestEvaluator:
    def test_run_creates_report(self):
        evaluator = Evaluator(envs=["GAME", "NAVWORLD"])
        report = evaluator.run(model_path="test/model", samples_per_env=50)
        assert "GAME" in report.results
        assert "NAVWORLD" in report.results
        assert report.results["GAME"].sample_count == 50

    def test_run_unknown_env(self):
        evaluator = Evaluator(envs=["NONEXISTENT"])
        try:
            evaluator.run(model_path="test")
            assert False, "Should raise"
        except KeyError:
            pass


# ── ExperimentTracker ──

class TestExperimentTracker:
    def test_load_existing(self):
        tracker = ExperimentTracker(
            os.path.join(os.path.dirname(__file__), "..", "experiments")
        )
        # v2.25 should exist
        exp = tracker.load("v2.25")
        assert exp is not None
        assert exp.id == "v2.25"

    def test_load_nonexistent(self):
        tracker = ExperimentTracker(
            os.path.join(os.path.dirname(__file__), "..", "experiments")
        )
        exp = tracker.load("v999.999")
        assert exp is None

    def test_list_experiments(self):
        tracker = ExperimentTracker(
            os.path.join(os.path.dirname(__file__), "..", "experiments")
        )
        exps = tracker.list_experiments()
        assert len(exps) > 0

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = ExperimentTracker(tmpdir)
            exp = Experiment(
                id="test-001",
                variable="lr",
                hypothesis="Lower lr improves stability",
                status="draft",
            )
            tracker.save(exp)
            loaded = tracker.load("test-001")
            assert loaded is not None
            assert loaded.variable == "lr"
            assert loaded.hypothesis == "Lower lr improves stability"

    def test_update_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = ExperimentTracker(tmpdir)
            exp = Experiment(id="test-002", variable="data", hypothesis="More data helps")
            tracker.save(exp)
            tracker.update_status("test-002", "running")
            loaded = tracker.load("test-002")
            assert loaded.status == "running"

    def test_experiment_to_dict_roundtrip(self):
        exp = Experiment(
            id="v1", variable="lr", hypothesis="h",
            status="completed", train_config={"lr": 1e-4},
            data_config={"GAME": 100}, results={"score": 0.5},
            notes="test note",
        )
        d = exp.to_dict()
        exp2 = Experiment.from_dict(d)
        assert exp2.id == exp.id
        assert exp2.variable == exp.variable
        assert exp2.train_config == exp.train_config
        assert exp2.results == exp.results
