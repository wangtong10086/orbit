"""Tests for Layer 1: forge/pipeline — data, eval, experiment."""

import sys
import os
import tempfile
import math
import json
from pathlib import Path
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forge.foundation.packing import Qwen3ConversationPacker
from forge.foundation.repository import LocalCanonicalRepository
from forge.control.experiment import Experiment, ExperimentStore
from forge.pipeline.data import (
    DataIngestPipeline,
    DatasetBuildPipeline,
    IngestReport,
)
from forge.pipeline.eval import EvaluationPipeline, EvalReport, EnvResult
from tests.eval_helpers import make_script_runner


class TestIngestReport:
    def test_total(self):
        r = IngestReport(accepted=3, dropped=1, invalid=1, duplicate=1)
        assert r.total == 6

    def test_summary(self):
        r = IngestReport(accepted=5, dropped=2, invalid=1, duplicate=0)
        s = r.summary()
        assert "5/8" in s

class TestDataIngestPipeline:
    def _navworld_record(self):
        return {
            "messages": [
                {"role": "system", "content": "你是一个旅行规划助手。"},
                {"role": "user", "content": "帮我规划从北京到上海的旅行"},
                {
                    "role": "assistant",
                    "content": "好的，让我调用工具帮您查询poi_search相关信息。",
                    "tool_calls": [{"id": "1", "function": {"name": "poi_search", "arguments": "{}"}}],
                },
                {"role": "tool", "content": '{"pois": []}', "tool_call_id": "1"},
                {
                    "role": "assistant",
                    "content": "让我再调用工具查询search_train_tickets火车票和around_search周边。",
                    "tool_calls": [{"id": "2", "function": {"name": "search_train_tickets", "arguments": "{}"}}],
                },
                {"role": "tool", "content": '{"trains": []}', "tool_call_id": "2"},
                {
                    "role": "assistant",
                    "content": "让我调用工具查看weather天气情况和direction路线。",
                    "tool_calls": [{"id": "3", "function": {"name": "weather", "arguments": "{}"}}],
                },
                {"role": "tool", "content": '{"weather": "sunny"}', "tool_call_id": "3"},
                {
                    "role": "assistant",
                    "content": "根据查询结果，我建议您考虑以下旅行方案。综合对比各种交通方式，推荐您选择高铁出行。因为高铁既快速又舒适，适合您的行程安排。"
                    + "x" * 220,
                },
            ],
            "env": "NAVWORLD",
            "score": 0.8,
        }

    def test_ingest_writes_to_repository_and_dedups_existing(self, tmp_path):
        repo = LocalCanonicalRepository(str(tmp_path))
        pipeline = DataIngestPipeline("NAVWORLD", repository=repo)
        record = self._navworld_record()

        report1 = pipeline.ingest([record], source="test")
        assert report1.accepted == 1
        assert repo.path_for("NAVWORLD").exists()

        report2 = pipeline.ingest([record], source="test")
        assert report2.duplicate == 1
        loaded = repo.load("NAVWORLD")
        assert len(loaded) == 1
        assert loaded[0]["messages"][2]["tool_calls"][0]["function"]["name"] == "poi_search"


class TestDatasetBuildPipeline:
    def _navworld_record(self):
        return TestDataIngestPipeline()._navworld_record()

    def test_build_uses_qwen3_packer(self, tmp_path):
        repo = LocalCanonicalRepository(str(tmp_path / "canonical"))
        repo.append("NAVWORLD", [self._navworld_record()])
        pipeline = DatasetBuildPipeline(
            repository=repo,
            packer=Qwen3ConversationPacker(),
        )
        output_path = tmp_path / "train.jsonl"
        report = pipeline.build(str(output_path), envs=["NAVWORLD"])

        assert report.total == 1
        with output_path.open() as handle:
            row = json.loads(handle.readline())
        assert "<tools>" in row["messages"][0]["content"]
        assert "<tool_call>" in row["messages"][2]["content"]
        assert any(m["role"] == "user" and "<tool_response>" in m["content"] for m in row["messages"])

    def test_package_surface_does_not_export_legacy_data_pipeline(self):
        import forge.pipeline as pipeline_package

        assert "DataPipeline" not in pipeline_package.__all__
        with pytest.raises(ImportError):
            exec("from forge.pipeline import DataPipeline", {})


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
        assert report.geo_mean == 0.0

    def test_summary(self):
        report = EvalReport(model_path="test_model")
        report.results = {"GAME": EnvResult(env_name="GAME", mean_score=50.0, sample_count=100)}
        s = report.summary()
        assert "test_model" in s
        assert "GAME" in s


class TestEvaluator:
    def test_run_creates_report(self, tmp_path):
        evaluator = EvaluationPipeline(
            envs=["GAME", "NAVWORLD"],
            runner=make_script_runner(tmp_path, {"GAME": [0.5, 0.6], "NAVWORLD": [0.2, 0.4]}),
        )
        report = evaluator.run(model_path="test/model", samples_per_env=50)
        assert "GAME" in report.results
        assert "NAVWORLD" in report.results
        assert report.results["GAME"].sample_count == 2
        assert report.results["GAME"].mean_score == pytest.approx(55.0)
        assert report.results["NAVWORLD"].mean_score == pytest.approx(30.0)

    def test_run_unknown_env(self, tmp_path):
        evaluator = EvaluationPipeline(
            envs=["NONEXISTENT"],
            runner=make_script_runner(tmp_path, {"GAME": [0.5]}),
        )
        try:
            evaluator.run(model_path="test")
            assert False, "Should raise"
        except KeyError:
            pass


# ── ExperimentStore ──

class TestExperimentStore:
    def test_load_existing(self):
        tracker = ExperimentStore(
            os.path.join(os.path.dirname(__file__), "..", "experiments")
        )
        # v2.25 should exist
        exp = tracker.load("v2.25")
        assert exp is not None
        assert exp.id == "v2.25"

    def test_load_nonexistent(self):
        tracker = ExperimentStore(
            os.path.join(os.path.dirname(__file__), "..", "experiments")
        )
        exp = tracker.load("v999.999")
        assert exp is None

    def test_list_experiments(self):
        tracker = ExperimentStore(
            os.path.join(os.path.dirname(__file__), "..", "experiments")
        )
        exps = tracker.list_experiments()
        assert len(exps) > 0

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = ExperimentStore(tmpdir)
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
            tracker = ExperimentStore(tmpdir)
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
