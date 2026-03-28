"""Tests for forge/training — SwiftConfig and SwiftBackend (ms-swift)."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forge.config import ForgeConfig
from forge.compute.base import GpuInstance
from forge.foundation.contracts import EvaluationSpec, TrainingLaunch, TrainingSpec
from forge.foundation.evaluation import ScriptEvaluationRunner
from forge.pipeline.training import TrainingPipeline
from forge.training.config import SwiftConfig, TrainConfig, TrainType, RlhfType, TunerType
from forge.training.providers import SshExecutionProvider, TargonBootstrapProvider, TargonImageProvider
from forge.training.sft import SwiftBackend, SftBackend
from tests.eval_helpers import make_script_runner


class TestSwiftConfig:
    def test_defaults(self):
        c = SwiftConfig()
        assert c.model == "Qwen/Qwen3-32B"
        assert c.learning_rate == 1e-4
        assert c.lora_rank == 64
        assert c.lora_alpha == 128
        assert c.quant_method == "bnb"
        assert c.max_length == 4096
        assert c.train_type == "sft"
        assert c.tuner_type == "lora"

    def test_override(self):
        c = SwiftConfig(learning_rate=5e-5, lora_rank=32, max_length=8192)
        assert c.learning_rate == 5e-5
        assert c.lora_rank == 32
        assert c.max_length == 8192

    def test_to_yaml_dict_sft(self):
        c = SwiftConfig()
        d = c.to_yaml_dict("/data/train.jsonl")
        assert d["model"] == "Qwen/Qwen3-32B"
        assert d["dataset"] == ["/data/train.jsonl"]
        assert d["tuner_type"] == "lora"
        assert d["lora_rank"] == 64
        assert d["quant_method"] == "bnb"
        assert "rlhf_type" not in d  # SFT mode

    def test_to_yaml_dict_rlhf(self):
        c = SwiftConfig(train_type="rlhf", rlhf_type="dpo", beta=0.1)
        d = c.to_yaml_dict("/data/dpo.jsonl")
        assert d["rlhf_type"] == "dpo"
        assert d["beta"] == 0.1

    def test_to_yaml_dict_grpo(self):
        c = SwiftConfig(train_type="rlhf", rlhf_type="grpo", num_generations=16,
                        reward_funcs=["accuracy", "format"])
        d = c.to_yaml_dict("/data/grpo.jsonl")
        assert d["rlhf_type"] == "grpo"
        assert d["num_generations"] == 16
        assert d["reward_funcs"] == ["accuracy", "format"]
        assert d["max_completion_length"] == 512

    def test_to_yaml_dict_full_param(self):
        c = SwiftConfig(tuner_type="full", quant_method=None, quant_bits=None)
        d = c.to_yaml_dict("/data/train.jsonl")
        assert d["tuner_type"] == "full"
        assert "lora_rank" not in d
        assert "quant_method" not in d

    def test_to_yaml_string(self):
        c = SwiftConfig()
        yaml_str = c.to_yaml("/data/train.jsonl")
        assert "model:" in yaml_str
        assert "Qwen/Qwen3-32B" in yaml_str
        assert "dataset:" in yaml_str

    def test_to_cli_args(self):
        c = SwiftConfig()
        args = c.to_cli_args("/data/train.jsonl")
        assert "--model" in args
        assert "Qwen/Qwen3-32B" in args
        assert "--dataset" in args
        assert "/data/train.jsonl" in args

    def test_swift_command_sft(self):
        c = SwiftConfig()
        cmd = c.swift_command("/data/train.jsonl")
        assert cmd.startswith("swift sft ")
        assert "--model" in cmd

    def test_swift_command_rlhf(self):
        c = SwiftConfig(train_type="rlhf", rlhf_type="grpo")
        cmd = c.swift_command("/data/grpo.jsonl")
        assert cmd.startswith("swift rlhf ")
        assert "--rlhf_type" in cmd

    def test_swift_command_from_yaml(self):
        c = SwiftConfig()
        cmd = c.swift_command_from_yaml("/root/config.yaml")
        assert cmd == "swift sft --config /root/config.yaml"

    def test_backward_compat_alias(self):
        """TrainConfig should be an alias for SwiftConfig."""
        assert TrainConfig is SwiftConfig
        c = TrainConfig()
        assert c.model == "Qwen/Qwen3-32B"

    def test_deepspeed(self):
        c = SwiftConfig(deepspeed="zero2")
        d = c.to_yaml_dict("/data/train.jsonl")
        assert d["deepspeed"] == "zero2"

    def test_adapters(self):
        c = SwiftConfig(adapters=["adapter1"], ref_adapters=["ref1"])
        d = c.to_yaml_dict("/data/train.jsonl")
        assert d["adapters"] == ["adapter1"]
        assert d["ref_adapters"] == ["ref1"]

    def test_enums(self):
        assert TrainType.SFT.value == "sft"
        assert RlhfType.GRPO.value == "grpo"
        assert TunerType.LORA.value == "lora"


class TestSwiftBackend:
    def test_validate_config_valid(self):
        backend = SwiftBackend()
        issues = backend.validate_config(SwiftConfig())
        assert issues == []

    def test_validate_lr_zero(self):
        backend = SwiftBackend()
        issues = backend.validate_config(SwiftConfig(learning_rate=0))
        assert any("learning_rate" in i for i in issues)

    def test_validate_lr_negative(self):
        backend = SwiftBackend()
        issues = backend.validate_config(SwiftConfig(learning_rate=-1e-4))
        assert any("learning_rate" in i for i in issues)

    def test_validate_lora_rank_zero(self):
        backend = SwiftBackend()
        issues = backend.validate_config(SwiftConfig(lora_rank=0))
        assert any("lora_rank" in i for i in issues)

    def test_validate_lora_rank_ignored_for_full(self):
        """lora_rank validation skipped when tuner_type=full."""
        backend = SwiftBackend()
        issues = backend.validate_config(SwiftConfig(tuner_type="full", lora_rank=0))
        assert not any("lora_rank" in i for i in issues)

    def test_validate_max_length_too_small(self):
        backend = SwiftBackend()
        issues = backend.validate_config(SwiftConfig(max_length=64))
        assert any("max_length" in i for i in issues)

    def test_validate_epochs_zero(self):
        backend = SwiftBackend()
        issues = backend.validate_config(SwiftConfig(num_train_epochs=0))
        assert any("num_train_epochs" in i for i in issues)

    def test_validate_invalid_train_type(self):
        backend = SwiftBackend()
        issues = backend.validate_config(SwiftConfig(train_type="invalid"))
        assert any("train_type" in i for i in issues)

    def test_validate_invalid_rlhf_type(self):
        backend = SwiftBackend()
        issues = backend.validate_config(SwiftConfig(train_type="rlhf", rlhf_type="invalid"))
        assert any("rlhf_type" in i for i in issues)

    def test_validate_rlhf_valid(self):
        backend = SwiftBackend()
        for rlhf_type in ["dpo", "grpo", "kto", "cpo", "simpo", "orpo", "ppo"]:
            issues = backend.validate_config(SwiftConfig(train_type="rlhf", rlhf_type=rlhf_type))
            assert issues == [], f"Unexpected issues for rlhf_type={rlhf_type}: {issues}"

    def test_generate_command(self):
        backend = SwiftBackend()
        cmd = backend.generate_command(SwiftConfig(), "/data/train.jsonl")
        assert isinstance(cmd, str)
        assert cmd.startswith("swift sft ")

    def test_generate_yaml(self):
        backend = SwiftBackend()
        yaml_str = backend.generate_yaml(SwiftConfig(), "/data/train.jsonl")
        assert isinstance(yaml_str, str)
        assert "model:" in yaml_str

    def test_backward_compat_alias(self):
        """SftBackend should be an alias for SwiftBackend."""
        assert SftBackend is SwiftBackend


class _FakeProvider:
    def __init__(self):
        self.launched = []

    async def launch_training(self, spec: TrainingSpec) -> TrainingLaunch:
        self.launched.append(spec)
        return TrainingLaunch(provider_name="fake", run_id="run-123")

    async def monitor_training(self, launch: TrainingLaunch) -> dict:
        return {"run_id": launch.run_id}


class TestTrainingPipeline:
    def test_launch_uses_explicit_provider(self):
        pipeline = TrainingPipeline()
        provider = _FakeProvider()
        spec = TrainingSpec(
            experiment_id="exp1",
            model="Qwen/Qwen3-32B",
            dataset_path="train.jsonl",
            train_config=SwiftConfig(output_dir="/tmp/ckpts").__dict__.copy(),
            environments=("GAME",),
            output_dir="/tmp/ckpts",
        )
        launch = asyncio.run(pipeline.launch(spec, provider))
        assert launch.provider_name == "fake"
        assert provider.launched == [spec]

    def test_launch_rejects_invalid_spec_before_provider(self):
        pipeline = TrainingPipeline()
        provider = _FakeProvider()
        spec = TrainingSpec(
            experiment_id="exp1",
            model="Qwen/Qwen3-32B",
            dataset_path="",
            train_config=SwiftConfig(output_dir="/tmp/ckpts").__dict__.copy(),
            environments=("GAME",),
            output_dir="/tmp/ckpts",
        )
        try:
            asyncio.run(pipeline.launch(spec, provider))
            assert False, "Should raise ValueError"
        except ValueError as exc:
            assert "dataset_path" in str(exc)
        assert provider.launched == []


class TestExecutionProviders:
    def test_provider_names_are_explicit(self):
        config = ForgeConfig()
        ssh = SshExecutionProvider(
            config,
            instance=GpuInstance(id="m1", backend="ssh", gpu_type="H200", status="ready", host="localhost"),
        )
        bootstrap = TargonBootstrapProvider(config, dataset_hf_repo="repo")
        image = TargonImageProvider(config, dataset_hf_repo="repo")
        assert ssh.name == "ssh"
        assert bootstrap.name == "targon-bootstrap"
        assert image.name == "targon-image"

    def test_targon_modes_keep_distinct_runtime_images(self):
        bootstrap = TargonBootstrapProvider(ForgeConfig(), dataset_hf_repo="repo")
        image = TargonImageProvider(ForgeConfig(), dataset_hf_repo="repo")
        assert bootstrap.image == "pytorch/pytorch:2.5.1-cuda12.4-cudnn9-devel"
        assert image.image == "wangtong123/affine-forge:latest"


class TestScriptEvaluationRunner:
    def test_runner_raises_on_nonzero_exit(self):
        runner = ScriptEvaluationRunner(command_executor=lambda cmd, env: (1, "", "boom"))
        try:
            runner.run_evaluation(EvaluationSpec(model_path="/tmp/model", environments=("GAME",)))
            assert False, "Should raise RuntimeError"
        except RuntimeError as exc:
            assert "boom" in str(exc)
