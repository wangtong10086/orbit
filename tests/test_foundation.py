"""Tests for Layer 0 foundation contracts and shared policies."""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from forge.foundation.contracts import EvaluationSpec, TrainingSpec
from forge.foundation.evaluation import ScriptEvaluationRunner
from forge.foundation.environment_catalog import default_environment_catalog
from forge.foundation.packing import Qwen3ConversationPacker
from forge.foundation.repository import LocalCanonicalRepository, canonical_fingerprint, env_to_filename
from forge.foundation.scoring import ScoringPolicy
from forge.pipeline.eval import EvaluationPipeline
from tests.eval_helpers import make_script_runner


class TestScoringPolicy:
    def test_strict_geo_mean_basic(self):
        assert ScoringPolicy.strict_geo_mean([4.0, 9.0]) == pytest.approx(6.0)

    def test_strict_geo_mean_zero_is_zero(self):
        assert ScoringPolicy.strict_geo_mean([10.0, 0.0]) == 0.0

    def test_strict_geo_mean_empty(self):
        assert ScoringPolicy.strict_geo_mean([]) == 0.0

    def test_strict_geo_mean_negative_raises(self):
        with pytest.raises(ValueError):
            ScoringPolicy.strict_geo_mean([1.0, -1.0])


class TestFoundationContracts:
    def test_training_spec_is_stable_dataclass(self):
        spec = TrainingSpec(
            experiment_id="v1",
            model="Qwen/Qwen3-32B",
            dataset_path="/tmp/data.jsonl",
            train_config={"learning_rate": 1e-4},
            environments=("GAME", "NAVWORLD"),
            output_dir="/tmp/checkpoints",
        )
        assert spec.environments == ("GAME", "NAVWORLD")

    def test_catalog_exposes_data_and_gem_envs(self):
        catalog = default_environment_catalog()
        assert catalog.has_data("GAME")
        assert catalog.has_gem("GAME")
        assert catalog.has_data("MEMORYGYM")
        assert not catalog.has_gem("MEMORYGYM")

    def test_evaluator_accepts_evaluation_spec(self, tmp_path: Path):
        evaluator = EvaluationPipeline(runner=make_script_runner(tmp_path, {"GAME": [0.4], "NAVWORLD": [0.8]}))
        report = evaluator.run_evaluation(
            EvaluationSpec(
                model_path="/tmp/model",
                environments=("GAME", "NAVWORLD"),
                samples_per_env=25,
            )
        )
        assert report.model_path == "/tmp/model"
        assert report.results["GAME"].sample_count == 1
        assert report.results["NAVWORLD"].sample_count == 1


class TestCanonicalRepository:
    def test_local_repository_append_load_and_exists(self, tmp_path: Path):
        repo = LocalCanonicalRepository(str(tmp_path))
        record = {
            "env": "GAME",
            "score": 0.5,
            "messages": [
                {"role": "system", "content": "You are a game player."},
                {"role": "user", "content": "Play chess"},
                {"role": "assistant", "content": "e4"},
            ],
        }
        fp = canonical_fingerprint(record)
        assert not repo.exists("GAME", fp)
        assert repo.append("GAME", [record]) == 1
        assert repo.exists("GAME", fp)
        loaded = repo.load("GAME")
        assert loaded == [record]

    def test_env_to_filename_supports_memorygym(self):
        assert env_to_filename("MEMORYGYM") == "memorygym.jsonl"


class TestConversationPackers:
    def test_qwen3_packer_formats_tool_calls_and_responses(self):
        packer = Qwen3ConversationPacker()
        packed = packer.pack(
            {
                "env": "NAVWORLD",
                "messages": [
                    {"role": "system", "content": "你是旅行助手"},
                    {
                        "role": "assistant",
                        "content": "我来查一下",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "weather",
                                    "arguments": '{"city":"上海"}',
                                }
                            }
                        ],
                    },
                    {"role": "tool", "content": '{"weather":"sunny"}', "tool_call_id": "call_1"},
                ],
            }
        )
        assert "<tools>" in packed[0]["content"]
        assert "<tool_call>" in packed[1]["content"]
        assert packed[2]["role"] == "user"
        assert "<tool_response>" in packed[2]["content"]


class TestScriptEvaluationRunner:
    def test_runner_executes_script_and_reads_summary(self, tmp_path: Path):
        runner = make_script_runner(tmp_path, {"GAME": [0.5, 0.0]})
        payload = runner.run_evaluation(
            EvaluationSpec(
                model_path="/tmp/model",
                environments=("GAME",),
                output_dir=str(tmp_path / "eval_out"),
            )
        )
        assert payload["summary"]["results"]["GAME"]["mean_score"] == pytest.approx(0.25)
