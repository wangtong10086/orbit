"""Tests for training config and control-side training pipeline."""

import asyncio
import json
import subprocess
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
from orbit.training.config import (
    LengthBucketingConfig,
    LengthBucketStageConfig,
    SwiftConfig,
    TrainType,
    RlhfType,
    TunerType,
    resolve_length_bucket_stages,
)
from orbit.training.sft import SwiftBackend
from tests.eval_helpers import make_script_runner
import scripts.eval_envs as eval_envs


class TestSwiftConfig:
    def test_defaults(self):
        c = SwiftConfig()
        assert c.model == "Qwen/Qwen3-32B"
        assert c.seed == 42
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
        assert d["seed"] == 42
        assert d["dataset"] == ["/data/train.jsonl"]
        assert d["tuner_type"] == "lora"
        assert d["lora_rank"] == 64
        assert d["quant_method"] == "bnb"
        assert d["report_to"] == "wandb"
        assert "wandb_project" not in d
        assert "wandb_run_name" not in d
        assert "reference_model" not in d
        assert "sample_weight_field" not in d
        assert "rlhf_type" not in d  # SFT mode

    def test_to_declared_dict_only_keeps_explicit_fields(self):
        c = SwiftConfig(learning_rate=5e-5, max_length=8192, report_to="none")
        d = c.to_declared_dict()
        assert d == {
            "learning_rate": 5e-5,
            "max_length": 8192,
            "report_to": "none",
        }

    def test_to_effective_dict_full_training_drops_lora_and_quant(self):
        c = SwiftConfig(
            tuner_type="full",
            quant_method="bnb",
            quant_bits=4,
            report_to="none",
        )
        d = c.to_effective_dict()
        assert d["tuner_type"] == "full"
        assert "lora_rank" not in d
        assert "lora_alpha" not in d
        assert "lora_dropout" not in d
        assert "target_modules" not in d
        assert "quant_method" not in d
        assert "quant_bits" not in d

    def test_to_effective_dict_sft_drops_rlhf_fields(self):
        c = SwiftConfig(
            train_type="sft",
            teacher_model="Qwen/Qwen3-8B",
            lmbda=0.5,
            sft_alpha=0.1,
            report_to="none",
        )
        d = c.to_effective_dict()
        assert d["train_type"] == "sft"
        assert "rlhf_type" not in d
        assert "teacher_model" not in d
        assert "teacher_adapters" not in d
        assert "lmbda" not in d
        assert "sft_alpha" not in d

    def test_to_effective_dict_external_gkd_drops_empty_teacher_model(self):
        c = SwiftConfig(
            train_type="rlhf",
            rlhf_type="gkd",
            teacher_model="",
            report_to="none",
            swift_passthrough={"teacher_model_server": "https://teacher.example/v1", "gkd_logits_topk": 20},
        )
        d = c.to_effective_dict()
        assert d["rlhf_type"] == "gkd"
        assert "teacher_model" not in d
        assert d["swift_passthrough"]["teacher_model_server"] == "https://teacher.example/v1"
        assert d["swift_passthrough"]["gkd_logits_topk"] == 20
        assert d["seq_kd"] is False

    def test_to_yaml_dict_includes_model_type_and_template_when_set(self):
        c = SwiftConfig(model="Qwen/Qwen2.5-0.5B-Instruct", model_type="qwen2", template="qwen2_5")
        d = c.to_yaml_dict("/data/train.jsonl")
        assert d["model_type"] == "qwen2"
        assert d["template"] == "qwen2_5"

    def test_to_yaml_dict_rlhf(self):
        c = SwiftConfig(train_type="rlhf", rlhf_type="dpo", beta=0.1)
        d = c.to_yaml_dict("/data/dpo.jsonl")
        assert d["rlhf_type"] == "dpo"
        assert d["beta"] == 0.1

    def test_to_yaml_dict_gkd(self):
        c = SwiftConfig(
            train_type="rlhf",
            rlhf_type="gkd",
            teacher_model="Qwen/Qwen2.5-7B-Instruct",
            lmbda=0.5,
            sft_alpha=0.1,
            seq_kd=False,
        )
        d = c.to_yaml_dict("/data/gkd.jsonl")
        assert d["rlhf_type"] == "gkd"
        assert d["teacher_model"] == "Qwen/Qwen2.5-7B-Instruct"
        assert d["lmbda"] == 0.5
        assert d["sft_alpha"] == 0.1
        assert d["seq_kd"] is False

    def test_to_yaml_dict_allows_swift_passthrough(self):
        c = SwiftConfig(
            train_type="rlhf",
            rlhf_type="gkd",
            teacher_model="Qwen/Qwen2.5-7B-Instruct",
            swift_passthrough={"gkd_logits_topk": 64},
        )
        d = c.to_yaml_dict("/data/gkd.jsonl")
        assert d["gkd_logits_topk"] == 64

    def test_to_yaml_dict_rejects_passthrough_key_overlap(self):
        c = SwiftConfig(swift_passthrough={"model": "override"})
        try:
            c.to_yaml_dict("/data/train.jsonl")
            assert False, "Expected duplicate passthrough key validation"
        except ValueError as exc:
            assert "swift_passthrough keys must not overlap" in str(exc)

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

    def test_resolve_length_bucket_stages_auto(self):
        config = LengthBucketingConfig(
            stages=[
                LengthBucketStageConfig(name="b8", max_length=8192),
                LengthBucketStageConfig(name="b16", max_length=16384),
                LengthBucketStageConfig(name="b32", max_length=32768),
            ]
        )
        stages = resolve_length_bucket_stages(config)
        assert [(stage.name, stage.bucket_min_length, stage.bucket_max_length) for stage in stages] == [
            ("b8", 0, 8192),
            ("b16", 8193, 16384),
            ("b32", 16385, None),
        ]

    def test_length_bucketing_manual_requires_relative_output_dir(self):
        try:
            LengthBucketingConfig(
                mode="manual",
                output_dir="/tmp/buckets",
                stages=[
                    LengthBucketStageConfig(
                        name="short",
                        max_length=4096,
                        bucket_min_length=0,
                        bucket_max_length=4096,
                    )
                ],
            )
            assert False, "Expected output_dir validation"
        except ValueError as exc:
            assert "relative to the bundle root" in str(exc)


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

    def test_validate_gkd_requires_teacher_model(self):
        backend = SwiftBackend()
        issues = backend.validate_config(SwiftConfig(train_type="rlhf", rlhf_type="gkd", teacher_model=""))
        assert (
            "teacher_model is required when train_type=rlhf and rlhf_type=gkd unless "
            "swift_passthrough.teacher_model_server is set"
        ) in issues

    def test_validate_gkd_allows_teacher_model_server_passthrough(self):
        backend = SwiftBackend()
        issues = backend.validate_config(
            SwiftConfig(
                train_type="rlhf",
                rlhf_type="gkd",
                teacher_model="",
                swift_passthrough={"teacher_model_server": "http://teacher.example:8000"},
            )
        )
        assert issues == []

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
        assert 'DATASET_PATH="${AFFINE_DATASET_PATH:-${BUNDLE_ROOT}/inputs/' in entrypoint
        assert 'sed "s|__AFFINE_DATASET_PATH__|${DATASET_PATH}|g"' in entrypoint
        assert 'cd "${BUNDLE_ROOT}"' in entrypoint

    def test_train_bundle_uses_remote_dataset_env_when_dataset_is_hf_staged(self, tmp_path):
        from orbit.tasks.training.bundle_builder import TrainBundleBuilder

        dataset = tmp_path / "train.jsonl"
        dataset.write_text('{"messages":[]}\n', encoding="utf-8")
        spec = TrainingSpec(
            experiment_id="exp-remote-dataset",
            model="Qwen/Qwen2.5-0.5B-Instruct",
            dataset_path=str(dataset),
            dataset_remote_repo="user/runtime-stage",
            dataset_remote_path="runtime-datasets/exp-remote-dataset/train.jsonl",
            dataset_remote_repo_type="model",
            train_config=SwiftConfig(output_dir="/tmp/out"),
            environments=("SMOKE",),
            output_dir="/tmp/out",
        )
        bundle = TrainBundleBuilder().build(str(tmp_path / "bundle"), spec=spec, overwrite=True)
        entrypoint = bundle.entrypoint_path.read_text(encoding="utf-8")
        job = bundle.load_job()
        assert not any(item.name == "dataset" for item in job.inputs)
        assert job.metadata["dataset_transport"] == "hf_staging"
        assert job.metadata["dataset_hf_repo"] == "user/runtime-stage"
        assert job.metadata["dataset_hf_path"] == "runtime-datasets/exp-remote-dataset/train.jsonl"
        assert 'DATASET_PATH="${AFFINE_DATASET_PATH:-}"' in entrypoint
        assert 'if [ -z "${DATASET_PATH}" ]; then echo "Dataset path not resolved before training launch" >&2; exit 1; fi' in entrypoint

    def test_train_bundle_escapes_local_model_path_in_swift_config(self, tmp_path):
        from orbit.tasks.training.bundle_builder import TrainBundleBuilder

        dataset = tmp_path / "train.jsonl"
        dataset.write_text('{"messages":[]}\n', encoding="utf-8")
        model_dir = tmp_path / "nested" / "model"
        model_dir.mkdir(parents=True)
        (model_dir / "config.json").write_text("{}\n", encoding="utf-8")
        spec = TrainingSpec(
            experiment_id="exp-local-model-path",
            model=str(model_dir),
            dataset_path=str(dataset),
            train_config=SwiftConfig(
                model=str(model_dir),
                output_dir="/tmp/out",
                model_type="qwen2",
                template="qwen2_5",
            ),
            environments=("SMOKE",),
            output_dir="/tmp/out",
        )
        bundle = TrainBundleBuilder().build(str(tmp_path / "bundle"), spec=spec, overwrite=True)
        entrypoint = bundle.entrypoint_path.read_text(encoding="utf-8")
        assert "ESCAPED_MODEL_PATH=$(printf '%s\\n' \"${MODEL_PATH}\" | sed 's/[&|]/\\\\&/g')" in entrypoint
        assert 'sed -i "0,/__AFFINE_LOCAL_MODEL_PATH__/s|__AFFINE_LOCAL_MODEL_PATH__|${ESCAPED_MODEL_PATH}|" "${BUNDLE_ROOT}/runtime/swift_config.resolved.yaml"' in entrypoint

    def test_train_bundle_stages_local_adapters_in_swift_config(self, tmp_path):
        from orbit.tasks.training.bundle_builder import TrainBundleBuilder

        dataset = tmp_path / "train.jsonl"
        dataset.write_text('{"messages":[]}\n', encoding="utf-8")
        adapter_dir = tmp_path / "adapter"
        adapter_dir.mkdir()
        (adapter_dir / "adapter_config.json").write_text('{"base_model_name_or_path": "Qwen/Qwen2.5-0.5B-Instruct"}\n', encoding="utf-8")
        (adapter_dir / "adapter_model.safetensors").write_text("stub\n", encoding="utf-8")
        spec = TrainingSpec(
            experiment_id="exp-local-adapters",
            model="Qwen/Qwen2.5-0.5B-Instruct",
            dataset_path=str(dataset),
            train_config=SwiftConfig(
                model="Qwen/Qwen2.5-0.5B-Instruct",
                train_type="rlhf",
                rlhf_type="dpo",
                adapters=[str(adapter_dir)],
                output_dir="/tmp/out",
                model_type="qwen2",
                template="qwen2_5",
            ),
            environments=("SMOKE",),
            output_dir="/tmp/out",
        )
        bundle = TrainBundleBuilder().build(str(tmp_path / "bundle"), spec=spec, overwrite=True)
        raw_yaml = (bundle.path / "inputs" / "swift_config.yaml").read_text(encoding="utf-8")
        entrypoint = bundle.entrypoint_path.read_text(encoding="utf-8")
        assert "__AFFINE_LOCAL_ADAPTER_PATH_0__" in raw_yaml
        assert 'ADAPTER_0_PATH="${BUNDLE_ROOT}/inputs/adapter-0-adapter"' in entrypoint
        assert 'sed -i "s|__AFFINE_LOCAL_ADAPTER_PATH_0__|${ESCAPED_ADAPTER_0_PATH}|g" "${BUNDLE_ROOT}/runtime/swift_config.resolved.yaml"' in entrypoint

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
        assert 'AFFINE_UPLOAD_ROOT="${BUNDLE_ROOT}/artifacts"' in entrypoint
        assert "AutoTokenizer.from_pretrained" in entrypoint
        assert "upload_folder(" in entrypoint
        assert "HF_TOKEN is required for post-training Hugging Face upload" in entrypoint

    def test_train_bundle_writes_bucketed_runtime_plan_and_scripts(self, tmp_path):
        from orbit.tasks.training.bundle_builder import TrainBundleBuilder

        dataset = tmp_path / "train.jsonl"
        dataset.write_text('{"messages":[{"role":"user","content":"hi"},{"role":"assistant","content":"hello"}]}\n', encoding="utf-8")
        spec = TrainingSpec(
            experiment_id="exp-bucketed-sft",
            model="Qwen/Qwen3-32B",
            dataset_path=str(dataset),
            train_config=SwiftConfig(
                model="Qwen/Qwen3-32B",
                train_type="sft",
                tuner_type="full",
                quant_method=None,
                quant_bits=None,
                output_dir="/tmp/out",
                report_to="none",
                num_gpus=8,
            ),
            bucketing=LengthBucketingConfig(
                stages=[
                    LengthBucketStageConfig(
                        name="b8",
                        max_length=8192,
                        train_overrides={"per_device_train_batch_size": 2, "gradient_accumulation_steps": 1},
                    ),
                    LengthBucketStageConfig(
                        name="b16",
                        max_length=16384,
                        train_overrides={"per_device_train_batch_size": 1, "gradient_accumulation_steps": 2},
                    ),
                    LengthBucketStageConfig(
                        name="b32",
                        max_length=32768,
                        train_overrides={"per_device_train_batch_size": 1, "gradient_accumulation_steps": 4},
                    ),
                ]
            ),
            environments=("GAME",),
            output_dir="/tmp/out",
        )
        bundle = TrainBundleBuilder().build(str(tmp_path / "bundle"), spec=spec, overwrite=True)
        entrypoint = bundle.entrypoint_path.read_text(encoding="utf-8")
        plan = json.loads((bundle.path / "inputs" / "length_bucket_plan.json").read_text(encoding="utf-8"))
        job = bundle.load_job()
        assert (bundle.path / "scripts" / "split_ms_swift_dataset_by_length.py").exists()
        assert (bundle.path / "scripts" / "run_bucketed_swift_training.py").exists()
        assert '"${ORBIT_PYTHON}" "${BUNDLE_ROOT}/scripts/split_ms_swift_dataset_by_length.py"' in entrypoint
        assert 'BUNDLE_WORKSPACE="$(cd "${BUNDLE_ROOT}/.." && pwd)"' in entrypoint
        assert '--workspace "${BUNDLE_WORKSPACE}"' in entrypoint
        assert '"${ORBIT_PYTHON}" "${BUNDLE_ROOT}/scripts/run_bucketed_swift_training.py"' in entrypoint
        assert plan["stages"][0]["name"] == "b8"
        assert plan["stages"][2]["bucket_max_length"] is None
        assert plan["stages"][1]["train_overrides"]["gradient_accumulation_steps"] == 2
        assert job.metadata["bucketed_training"] is True
        assert job.metadata["bucket_stage_count"] == 3
        assert any(output.name == "bucket_manifest" for output in job.expected_outputs)

    def test_bucketed_runner_uses_base_model_plus_previous_adapter_for_lora(self, tmp_path):
        workspace = tmp_path / "workspace"
        (workspace / "bundle" / "runtime").mkdir(parents=True)
        (workspace / "bundle" / "artifacts" / "checkpoints-short" / "v0" / "checkpoint-1").mkdir(parents=True)
        medium_dataset = workspace / "bundle" / "runtime" / "bucketed" / "medium.jsonl"
        medium_dataset.parent.mkdir(parents=True, exist_ok=True)
        medium_dataset.write_text('{"messages":[]}\n', encoding="utf-8")
        short_dataset = workspace / "bundle" / "runtime" / "bucketed" / "short.jsonl"
        short_dataset.write_text('{"messages":[]}\n', encoding="utf-8")

        base_config = {
            "model": "Qwen/Qwen3-0.6B",
            "train_type": "sft",
            "tuner_type": "lora",
            "adapters": [],
            "output_dir": "artifacts/checkpoints",
            "packing": False,
        }
        (workspace / "bundle" / "runtime" / "swift_config.resolved.yaml").write_text(
            json.dumps(base_config), encoding="utf-8"
        )

        import yaml

        (workspace / "bundle" / "runtime" / "swift_config.resolved.yaml").write_text(
            yaml.safe_dump(base_config, sort_keys=False),
            encoding="utf-8",
        )
        plan = {
            "stages": [
                {"name": "short", "max_length": 256, "train_overrides": {}},
                {"name": "medium", "max_length": 1024, "train_overrides": {}},
            ]
        }
        manifest = {
            "buckets": {
                "short": {"path": str(short_dataset), "count": 1},
                "medium": {"path": str(medium_dataset), "count": 1},
            }
        }
        plan_path = tmp_path / "plan.json"
        manifest_path = tmp_path / "manifest.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                "scripts/run_bucketed_swift_training.py",
                "--workspace",
                str(workspace),
                "--base-config",
                str(workspace / "bundle" / "runtime" / "swift_config.resolved.yaml"),
                "--plan-json",
                str(plan_path),
                "--manifest",
                str(manifest_path),
                "--train-type",
                "sft",
                "--dry-run",
            ],
            cwd=str(Path(__file__).resolve().parents[1]),
            check=True,
            text=True,
            capture_output=True,
        )
        payload = json.loads(result.stdout)
        assert payload[0]["model"] == "Qwen/Qwen3-0.6B"
        assert payload[0]["adapters"] == []
        assert payload[1]["model"] == "Qwen/Qwen3-0.6B"
        assert payload[1]["adapters"] == ["artifacts/checkpoints-short/v*/checkpoint-*"]

    def test_train_bundle_stages_local_gkd_teacher_inputs(self, tmp_path):
        from orbit.tasks.training.bundle_builder import TrainBundleBuilder

        dataset = tmp_path / "train.jsonl"
        dataset.write_text('{"messages":[{"role":"user","content":"hi"},{"role":"assistant","content":"hello"}]}\n', encoding="utf-8")
        teacher_dir = tmp_path / "teacher-model"
        teacher_dir.mkdir()
        (teacher_dir / "config.json").write_text("{}\n", encoding="utf-8")
        teacher_adapter = tmp_path / "teacher-adapter"
        teacher_adapter.mkdir()
        (teacher_adapter / "adapter_config.json").write_text('{"base_model_name_or_path": "Qwen/Qwen2.5-0.5B-Instruct"}\n', encoding="utf-8")
        spec = TrainingSpec(
            experiment_id="exp-gkd",
            model="Qwen/Qwen2.5-0.5B-Instruct",
            dataset_path=str(dataset),
            train_config=SwiftConfig(
                model="Qwen/Qwen2.5-0.5B-Instruct",
                train_type="rlhf",
                rlhf_type="gkd",
                model_type="qwen2",
                template="qwen2_5",
                output_dir="/tmp/out",
                teacher_model=str(teacher_dir),
                teacher_adapters=[str(teacher_adapter)],
                swift_passthrough={"gkd_logits_topk": 64},
            ),
            environments=("GAME",),
            output_dir="/tmp/out",
        )
        bundle = TrainBundleBuilder().build(str(tmp_path / "bundle"), spec=spec, overwrite=True)
        raw_yaml = (bundle.inputs_dir / "swift_config.yaml").read_text(encoding="utf-8")
        entrypoint = bundle.entrypoint_path.read_text(encoding="utf-8")
        job = bundle.load_job()
        assert "swift rlhf --config" in entrypoint
        assert "__AFFINE_LOCAL_TEACHER_MODEL_PATH__" in raw_yaml
        assert "__AFFINE_LOCAL_TEACHER_ADAPTER_PATH_0__" in raw_yaml
        assert "gkd_logits_topk: 64" in raw_yaml
        assert 'cd "${BUNDLE_ROOT}"' in entrypoint
        assert 'native GKD run: checking runtime packages' in entrypoint
        assert "native GKD runtime missing required packages" in entrypoint
        assert "('torch', 'transformers', 'swift', 'vllm')" in entrypoint
        assert "TEACHER_MODEL_PATH" in entrypoint
        assert "TEACHER_ADAPTER_0_PATH" in entrypoint
        assert 'sed -i "s|__AFFINE_LOCAL_TEACHER_MODEL_PATH__|${ESCAPED_TEACHER_MODEL_PATH}|g" "${BUNDLE_ROOT}/runtime/swift_config.resolved.yaml"' in entrypoint
        assert job.metadata["rlhf_type"] == "gkd"
        assert job.metadata["requires_vllm_runtime"] is True

    def test_train_bundle_uses_torchrun_for_multi_gpu_gkd(self, tmp_path):
        from orbit.tasks.training.bundle_builder import TrainBundleBuilder

        dataset = tmp_path / "train.jsonl"
        dataset.write_text('{"messages":[{"role":"user","content":"hi"},{"role":"assistant","content":"hello"}]}\n', encoding="utf-8")
        spec = TrainingSpec(
            experiment_id="exp-gkd-multi-gpu",
            model="Qwen/Qwen3-32B",
            dataset_path=str(dataset),
            train_config=SwiftConfig(
                model="Qwen/Qwen3-32B",
                train_type="rlhf",
                rlhf_type="gkd",
                teacher_model="Qwen/Qwen3-32B",
                model_type="qwen3",
                template="qwen3",
                output_dir="/tmp/out",
                tuner_type="full",
                quant_method=None,
                quant_bits=None,
                deepspeed="zero3",
                num_gpus=8,
            ),
            environments=("GAME",),
            output_dir="/tmp/out",
        )
        bundle = TrainBundleBuilder().build(str(tmp_path / "bundle"), spec=spec, overwrite=True)
        entrypoint = bundle.entrypoint_path.read_text(encoding="utf-8")
        raw_cfg = (bundle.inputs_dir / "swift_config.yaml").read_text(encoding="utf-8")
        assert "NPROC_PER_NODE=8 swift rlhf --config" in entrypoint
        assert "teacher_model: Qwen/Qwen3-32B" in raw_cfg
        assert "rlhf_type: gkd" in raw_cfg

    def test_train_bundle_supports_full_zero3_gkd(self, tmp_path):
        from orbit.tasks.training.bundle_builder import TrainBundleBuilder

        dataset = tmp_path / "train.jsonl"
        dataset.write_text('{"messages":[{"role":"user","content":"hi"},{"role":"assistant","content":"hello"}]}\n', encoding="utf-8")
        spec = TrainingSpec(
            experiment_id="exp-gkd-full-zero3",
            model="Qwen/Qwen3-32B",
            dataset_path=str(dataset),
            train_config=SwiftConfig(
                model="Qwen/Qwen3-32B",
                train_type="rlhf",
                rlhf_type="gkd",
                teacher_model="",
                model_type="qwen3",
                template="qwen3",
                output_dir="/tmp/out",
                tuner_type="full",
                quant_method=None,
                quant_bits=None,
                deepspeed="zero3",
                num_gpus=4,
                swift_passthrough={
                    "teacher_model_server": "https://teacher.example/v1",
                    "gkd_logits_topk": 20,
                    "max_steps": 1,
                },
            ),
            environments=("GAME",),
            output_dir="/tmp/out",
        )
        bundle = TrainBundleBuilder().build(str(tmp_path / "bundle"), spec=spec, overwrite=True)
        raw_cfg = (bundle.inputs_dir / "swift_config.yaml").read_text(encoding="utf-8")
        assert "tuner_type: full" in raw_cfg
        assert "deepspeed: zero3" in raw_cfg
        assert "quant_method" not in raw_cfg
        assert "quant_bits" not in raw_cfg
        assert "teacher_model_server: https://teacher.example/v1" in raw_cfg
        assert "gkd_logits_topk: 20" in raw_cfg



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
