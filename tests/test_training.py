"""Tests for training config and control-side training pipeline."""

import asyncio
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from orbit.config import OrbitConfig
from orbit.core.execution.bundle import JobBundle
from orbit.foundation.contracts import EvaluationSpec, TrainingSpec
from orbit.foundation.evaluation import ScriptEvaluationRunner
from orbit.core.contracts.execution import (
    ExecutionRequest,
    LaunchModeKind,
    LaunchModeSpec,
    PlacementKind,
    PlacementSpec,
    RunHandle,
)
from orbit.pipeline.training import TrainingPipeline
from orbit.training.config import SwiftConfig, TrainType, RlhfType, TunerType
from orbit.training.sft import SwiftBackend
from tests.eval_helpers import make_script_runner
import scripts.eval_envs as eval_envs


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
        assert c.report_to == "wandb"
        assert c.wandb_project == "orbit"

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
        assert d["report_to"] == "wandb"
        assert d["wandb_project"] == "orbit"
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

    def test_to_yaml_dict_full_param_drops_quantization_fields(self):
        c = SwiftConfig(tuner_type="full", quant_method="bnb", quant_bits=4)
        d = c.to_yaml_dict("/data/train.jsonl")
        assert d["tuner_type"] == "full"
        assert "quant_method" not in d
        assert "quant_bits" not in d

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

    def test_validate_full_rejects_quantization(self):
        backend = SwiftBackend()
        issues = backend.validate_config(SwiftConfig(tuner_type="full", quant_method="bnb", quant_bits=4))
        assert "quant_method must be unset when tuner_type=full" in issues
        assert "quant_bits must be unset when tuner_type=full" in issues

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

    def test_train_bundle_resolves_dataset_path_at_runtime(self, tmp_path):
        from orbit.tasks.training.bundle_builder import TrainBundleBuilder

        dataset = tmp_path / "train.jsonl"
        dataset.write_text('{"messages":[]}\n', encoding="utf-8")
        spec = TrainingSpec(
            experiment_id="exp-runtime-dataset",
            model="Qwen/Qwen2.5-0.5B-Instruct",
            dataset_path=str(dataset),
            train_config=SwiftConfig(output_dir="/tmp/out"),
            environments=("SMOKE",),
            output_dir="/tmp/out",
        )
        bundle = TrainBundleBuilder().build(str(tmp_path / "bundle"), spec=spec, overwrite=True)
        raw_yaml = (bundle.path / "inputs" / "swift_config.yaml").read_text(encoding="utf-8")
        entrypoint = bundle.entrypoint_path.read_text(encoding="utf-8")
        assert "__AFFINE_DATASET_PATH__" in raw_yaml
        assert "swift_config.resolved.yaml" in entrypoint
        assert 'DATASET_PATH="${BUNDLE_ROOT}/inputs/' in entrypoint
        assert 'sed "s|__AFFINE_DATASET_PATH__|${DATASET_PATH}|g"' in entrypoint

    def test_train_bundle_uses_post_training_hf_upload_wrapper(self, tmp_path):
        from orbit.tasks.training.bundle_builder import TrainBundleBuilder

        dataset = tmp_path / "train.jsonl"
        dataset.write_text('{"messages":[]}\n', encoding="utf-8")
        spec = TrainingSpec(
            experiment_id="exp-hf-upload",
            model="Qwen/Qwen2.5-0.5B-Instruct",
            dataset_path=str(dataset),
            train_config=SwiftConfig(
                output_dir="/tmp/out",
                push_to_hub=True,
                hub_model_id="alice/test-model",
                use_hf=True,
            ),
            environments=("SMOKE",),
            output_dir="/tmp/out",
        )
        bundle = TrainBundleBuilder().build(str(tmp_path / "bundle"), spec=spec, overwrite=True)
        raw_yaml = (bundle.path / "inputs" / "swift_config.yaml").read_text(encoding="utf-8")
        entrypoint = bundle.entrypoint_path.read_text(encoding="utf-8")
        assert "push_to_hub" not in raw_yaml
        assert "hub_model_id" not in raw_yaml
        assert "AFFINE_HUB_MODEL_ID" in entrypoint
        assert "AFFINE_UPLOAD_STAGING" in entrypoint
        assert "AutoTokenizer.from_pretrained" in entrypoint
        assert "upload_folder(" in entrypoint
        assert "HF_TOKEN is required for post-training Hugging Face upload" in entrypoint



class _FakeRuntime:
    def __init__(self):
        self.launched = []

    async def run(self, request: ExecutionRequest) -> RunHandle:
        bundle = JobBundle(request.bundle_path)
        self.launched.append((bundle.load_job(), request, bundle.path))
        return RunHandle(runtime_kind="fake", run_id="run-123", target_id="fake-target", bundle_path=str(bundle.path))

    async def status(self, handle):
        raise NotImplementedError

    async def logs(self, handle, tail=100):
        raise NotImplementedError

    async def collect(self, handle):
        raise NotImplementedError

    async def terminate(self, handle):
        raise NotImplementedError


class TestTrainingPipeline:
    def test_launch_renders_bundle_and_uses_runtime(self, tmp_path):
        pipeline = TrainingPipeline()
        runtime = _FakeRuntime()
        dataset = tmp_path / "train.jsonl"
        dataset.write_text('{"messages":[]}\n')
        spec = TrainingSpec(
            experiment_id="exp1",
            model="Qwen/Qwen3-32B",
            dataset_path=str(dataset),
            train_config=SwiftConfig(output_dir="/tmp/ckpts"),
            environments=("GAME",),
            output_dir="/tmp/ckpts",
        )
        launch = asyncio.run(
            pipeline.launch(
                spec,
                runtime,
                bundle_dir=str(tmp_path / "bundle"),
                execution_request=ExecutionRequest(
                    bundle_path="",
                    placement=PlacementSpec(kind=PlacementKind.LOCAL),
                    launch_mode=LaunchModeSpec(kind=LaunchModeKind.DOCKER_IMAGE),
                ),
            )
        )
        assert launch.runtime_kind == "fake"
        assert runtime.launched
        rendered_job, request, bundle_path = runtime.launched[0]
        assert rendered_job.job_id == "exp1"
        assert Path(bundle_path).name == "bundle"

    def test_launch_rejects_invalid_spec_before_runtime(self, tmp_path):
        pipeline = TrainingPipeline()
        runtime = _FakeRuntime()
        spec = TrainingSpec(
            experiment_id="exp1",
            model="Qwen/Qwen3-32B",
            dataset_path="",
            train_config=SwiftConfig(output_dir="/tmp/ckpts"),
            environments=("GAME",),
            output_dir="/tmp/ckpts",
        )
        try:
            asyncio.run(pipeline.launch(spec, runtime, bundle_dir=str(tmp_path / "bundle")))
            assert False, "Should raise ValueError"
        except ValueError as exc:
            assert "dataset_path" in str(exc)
        assert runtime.launched == []


class TestScriptEvaluationRunner:
    def test_runner_raises_on_nonzero_exit(self):
        runner = ScriptEvaluationRunner(command_executor=lambda cmd, env: (1, "", "boom"))
        try:
            runner.run_evaluation(EvaluationSpec(model_path="/tmp/model", environments=("GAME",)))
            assert False, "Should raise RuntimeError"
        except RuntimeError as exc:
            assert "boom" in str(exc)

    def test_runner_adds_affinetes_dir_to_pythonpath(self, tmp_path):
        captured = {}
        output_dir = tmp_path / "eval"
        output_dir.mkdir()
        (output_dir / "eval_summary.json").write_text('{"results":{"GAME":{}}}')

        def executor(cmd, env):
            captured["cmd"] = cmd
            captured["env"] = env
            return 0, "", ""

        runner = ScriptEvaluationRunner(command_executor=executor)
        runner.run_evaluation(
            EvaluationSpec(
                model_path="/tmp/model",
                environments=("GAME",),
                output_dir=str(output_dir),
                affinetes_dir="/home/wangtong/affinetes",
            )
        )

        assert captured["env"]["PYTHONPATH"].startswith("/home/wangtong/affinetes")

    def test_runner_falls_back_to_repo_sibling_affinetes_dir(self, tmp_path, monkeypatch):
        captured = {}
        output_dir = tmp_path / "eval"
        output_dir.mkdir()
        (output_dir / "eval_summary.json").write_text('{"results":{"GAME":{}}}')

        def executor(cmd, env):
            captured["cmd"] = cmd
            captured["env"] = env
            return 0, "", ""

        monkeypatch.setattr("orbit.foundation.evaluation._resolve_affinetes_dir", lambda _: "/resolved/affinetes")

        runner = ScriptEvaluationRunner(command_executor=executor)
        runner.run_evaluation(
            EvaluationSpec(
                model_path="/tmp/model",
                environments=("GAME",),
                output_dir=str(output_dir),
                affinetes_dir="/root/affinetes",
            )
        )

        assert "/resolved/affinetes" in captured["cmd"]
        assert captured["env"]["PYTHONPATH"].startswith("/resolved/affinetes")

    def test_runner_raises_when_summary_reports_env_error(self, tmp_path):
        output_dir = tmp_path / "eval"
        output_dir.mkdir()
        (output_dir / "eval_summary.json").write_text(
            json.dumps({"results": {"GAME": {"error": "docker permission denied"}}})
        )

        runner = ScriptEvaluationRunner(command_executor=lambda cmd, env: (0, "", ""))
        try:
            runner.run_evaluation(
                EvaluationSpec(
                    model_path="/tmp/model",
                    environments=("GAME",),
                    output_dir=str(output_dir),
                )
            )
            assert False, "Should raise RuntimeError"
        except RuntimeError as exc:
            assert "docker permission denied" in str(exc)

    def test_runner_mirrors_proxy_env_names(self, tmp_path, monkeypatch):
        captured = {}
        output_dir = tmp_path / "eval"
        output_dir.mkdir()
        (output_dir / "eval_summary.json").write_text('{"results":{"GAME":{}}}')
        monkeypatch.setenv("http_proxy", "http://127.0.0.1:10808")
        monkeypatch.delenv("HTTP_PROXY", raising=False)

        def executor(cmd, env):
            captured["env"] = env
            return 0, "", ""

        runner = ScriptEvaluationRunner(command_executor=executor)
        runner.run_evaluation(
            EvaluationSpec(
                model_path="/tmp/model",
                environments=("GAME",),
                output_dir=str(output_dir),
            )
        )

        assert captured["env"]["http_proxy"] == "http://127.0.0.1:10808"
        assert captured["env"]["HTTP_PROXY"] == "http://127.0.0.1:10808"


class TestEvalScriptBuilds:
    def test_build_images_passes_proxy_buildargs(self, monkeypatch):
        calls = []
        monkeypatch.setenv("http_proxy", "http://127.0.0.1:10808")
        monkeypatch.delenv("HTTP_PROXY", raising=False)
        monkeypatch.setattr(eval_envs.os.path, "isdir", lambda path: True)
        monkeypatch.setattr(eval_envs.af, "build_image_from_env", lambda **kwargs: calls.append(kwargs))

        asyncio.run(eval_envs.build_images("/tmp/affinetes", ["GAME"]))

        assert calls[0]["buildargs"]["http_proxy"] == "http://127.0.0.1:10808"
        assert calls[0]["buildargs"]["HTTP_PROXY"] == "http://127.0.0.1:10808"

    def test_evaluate_env_cleans_partial_containers_before_retry(self, monkeypatch, tmp_path):
        load_calls = []
        cleanup_calls = []

        class FakeEnv:
            async def evaluate(self, **kwargs):
                return {"score": 1.0}

            async def cleanup(self):
                return None

        def fake_load_env(**kwargs):
            load_calls.append(kwargs)
            if len(load_calls) == 1:
                raise RuntimeError("bridge health check timed out")
            return FakeEnv()

        monkeypatch.setattr(eval_envs.af, "load_env", fake_load_env)
        monkeypatch.setattr(eval_envs, "cleanup_partial_env_containers", lambda image_tag: cleanup_calls.append(image_tag))

        summary = asyncio.run(
            eval_envs.evaluate_env(
                "GAME",
                "Qwen/Qwen2.5-0.5B-Instruct",
                "http://localhost:30000/v1",
                "test-key",
                1,
                42,
                str(tmp_path),
                2,
            )
        )

        assert cleanup_calls == ["openspiel:eval"]
        assert load_calls[0]["replicas"] == 2
        assert load_calls[0]["host_network"] is False
        assert load_calls[1]["replicas"] == 1
        assert load_calls[1]["host_network"] is True
        assert summary["mean_score"] == 1.0

    def test_evaluate_env_maps_amap_api_key_alias(self, monkeypatch, tmp_path):
        load_calls = []

        class FakeEnv:
            async def evaluate(self, **kwargs):
                return {"score": 1.0}

            async def cleanup(self):
                return None

        monkeypatch.setenv("AMAP_API_KEY", "alias-key")
        monkeypatch.delenv("AMAP_MAPS_API_KEY", raising=False)
        monkeypatch.setattr(eval_envs.af, "load_env", lambda **kwargs: load_calls.append(kwargs) or FakeEnv())

        asyncio.run(
            eval_envs.evaluate_env(
                "NAVWORLD",
                "Qwen/Qwen2.5-0.5B-Instruct",
                "http://localhost:30000/v1",
                "test-key",
                1,
                42,
                str(tmp_path),
                1,
            )
        )

        assert load_calls[0]["env_vars"]["AMAP_MAPS_API_KEY"] == "alias-key"
