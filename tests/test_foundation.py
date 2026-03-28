"""Tests for Layer 0 foundation contracts and shared policies."""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from forge.foundation.contracts import EvaluationSpec, TrainingSpec
from forge.foundation.environment_catalog import default_environment_catalog
from forge.foundation.scoring import ScoringPolicy
from forge.pipeline.eval import Evaluator


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

    def test_evaluator_accepts_evaluation_spec(self):
        evaluator = Evaluator()
        report = evaluator.run_evaluation(
            EvaluationSpec(
                model_path="/tmp/model",
                environments=("GAME", "NAVWORLD"),
                samples_per_env=25,
            )
        )
        assert report.model_path == "/tmp/model"
        assert report.results["GAME"].sample_count == 25
        assert report.results["NAVWORLD"].sample_count == 25
