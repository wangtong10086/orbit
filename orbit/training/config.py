"""Training configuration for ms-swift based training."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import Field, model_validator

from orbit.foundation.schema import JsonValue, StrictModel
from orbit.integrations.ms_swift_offline_topk import (
    DEFAULT_TEACHER_DATA_MODE,
    DEFAULT_TEACHER_RESPONSE_TOKEN_IDS_FIELD,
    DEFAULT_TEACHER_TOPK_INDICES_FIELD,
    DEFAULT_TEACHER_TOPK_LOGPROBS_FIELD,
    DEFAULT_TEACHER_TOPK_STORAGE_DTYPE,
)


class TrainType(str, Enum):
    SFT = "sft"
    RLHF = "rlhf"
    PT = "pt"


class RlhfType(str, Enum):
    DPO = "dpo"
    GRPO = "grpo"
    KTO = "kto"
    CPO = "cpo"
    SIMPO = "simpo"
    ORPO = "orpo"
    PPO = "ppo"
    GKD = "gkd"


class TunerType(str, Enum):
    LORA = "lora"
    FULL = "full"


class LengthBucketMode(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"


class LengthBucketStageConfig(StrictModel):
    name: str
    max_length: int
    bucket_min_length: int | None = None
    bucket_max_length: int | None = None
    train_overrides: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_stage(self) -> "LengthBucketStageConfig":
        if self.max_length < 128:
            raise ValueError("bucket stage max_length must be >= 128")
        if self.bucket_min_length is not None and self.bucket_min_length < 0:
            raise ValueError("bucket_min_length must be >= 0 when set")
        if self.bucket_max_length is not None and self.bucket_max_length < 1:
            raise ValueError("bucket_max_length must be >= 1 when set")
        if (
            self.bucket_min_length is not None
            and self.bucket_max_length is not None
            and self.bucket_min_length > self.bucket_max_length
        ):
            raise ValueError("bucket_min_length must be <= bucket_max_length")
        return self


class LengthBucketingConfig(StrictModel):
    mode: LengthBucketMode = LengthBucketMode.AUTO
    tokenizer_model: str = ""
    workers: int = 4
    batch_size: int = 64
    output_dir: str = "runtime/bucketed"
    stages: list[LengthBucketStageConfig]

    @model_validator(mode="after")
    def _validate_bucketing(self) -> "LengthBucketingConfig":
        if not self.stages:
            raise ValueError("bucketing.stages must contain at least one stage")
        if self.workers < 1:
            raise ValueError("bucketing.workers must be >= 1")
        if self.batch_size < 1:
            raise ValueError("bucketing.batch_size must be >= 1")
        if Path(self.output_dir).is_absolute():
            raise ValueError("bucketing.output_dir must be relative to the bundle root")
        names = [stage.name for stage in self.stages]
        if len(set(names)) != len(names):
            raise ValueError("bucketing stage names must be unique")
        max_lengths = [stage.max_length for stage in self.stages]
        if max_lengths != sorted(max_lengths):
            raise ValueError("bucketing stages must be ordered by increasing max_length")
        if self.mode == LengthBucketMode.AUTO:
            for stage in self.stages:
                if stage.bucket_min_length is not None or stage.bucket_max_length is not None:
                    raise ValueError(
                        "auto bucketing stages must not set bucket_min_length or bucket_max_length"
                    )
        return self


class ResolvedLengthBucketStage(StrictModel):
    name: str
    max_length: int
    bucket_min_length: int = 0
    bucket_max_length: int | None = None
    train_overrides: dict[str, JsonValue] = Field(default_factory=dict)


def merge_swift_config_overrides(base: "SwiftConfig", overrides: dict[str, JsonValue]) -> "SwiftConfig":
    payload = base.model_dump(mode="json")
    merged_overrides = dict(overrides)
    if "swift_passthrough" in merged_overrides:
        override_passthrough = merged_overrides.pop("swift_passthrough")
        if not isinstance(override_passthrough, dict):
            raise ValueError("stage train_overrides.swift_passthrough must be a mapping")
        payload["swift_passthrough"] = {
            **payload.get("swift_passthrough", {}),
            **override_passthrough,
        }
    payload.update(merged_overrides)
    return SwiftConfig.model_validate(payload)


def resolve_length_bucket_stages(config: LengthBucketingConfig) -> list[ResolvedLengthBucketStage]:
    resolved: list[ResolvedLengthBucketStage] = []
    previous_max = 0
    for index, stage in enumerate(config.stages):
        if config.mode == LengthBucketMode.MANUAL:
            min_length = stage.bucket_min_length if stage.bucket_min_length is not None else 0
            max_length = stage.bucket_max_length
        else:
            min_length = 0 if index == 0 else previous_max + 1
            max_length = None if index == len(config.stages) - 1 else stage.max_length
        resolved.append(
            ResolvedLengthBucketStage(
                name=stage.name,
                max_length=stage.max_length,
                bucket_min_length=min_length,
                bucket_max_length=max_length,
                train_overrides=stage.train_overrides,
            )
        )
        previous_max = stage.max_length
    return resolved


class SwiftConfig(StrictModel):
    """Configuration for ms-swift training runs."""

    model: str = "Qwen/Qwen3-32B"
    seed: int = 42
    model_type: str = ""
    template: str = ""
    dtype: str = "bfloat16"
    attn_impl: str = "sdpa"

    train_type: str = "sft"
    rlhf_type: str = "dpo"

    tuner_type: str = "lora"
    lora_rank: int = 64
    lora_alpha: int = 128
    lora_dropout: float = 0.05
    target_modules: str = "all-linear"

    quant_method: str | None = "bnb"
    quant_bits: int | None = 4

    learning_rate: float = 1e-4
    num_train_epochs: int = 1
    per_device_train_batch_size: int = 2
    gradient_accumulation_steps: int = 8
    warmup_ratio: float = 0.03
    weight_decay: float = 0.01
    max_grad_norm: float = 0.3
    lr_scheduler_type: str = "cosine"

    max_length: int = 4096
    packing: bool = True
    dataset_num_proc: int = 4

    output_dir: str = "/root/checkpoints"
    save_steps: int = 100
    save_total_limit: int = 3
    logging_steps: int = 10

    deepspeed: str | None = None
    gradient_checkpointing: bool = True

    use_hf: bool = True
    push_to_hub: bool = False
    hub_model_id: str = ""

    beta: float | None = None
    max_completion_length: int = 512
    num_generations: int = 8
    reward_funcs: list[str] = Field(default_factory=list)

    adapters: list[str] = Field(default_factory=list)
    ref_adapters: list[str] = Field(default_factory=list)

    num_gpus: int = 1

    reference_model: str = ""
    reference_kl_coef: float | None = None
    sample_weight_field: str = ""
    loss_region_field: str = ""
    teacher_model: str = ""
    teacher_adapters: list[str] = Field(default_factory=list)
    teacher_model_type: str = ""
    teacher_model_revision: str = ""
    teacher_deepspeed: str | None = None
    teacher_data_mode: str = DEFAULT_TEACHER_DATA_MODE
    teacher_topk_indices_field: str = DEFAULT_TEACHER_TOPK_INDICES_FIELD
    teacher_topk_logprobs_field: str = DEFAULT_TEACHER_TOPK_LOGPROBS_FIELD
    teacher_response_token_ids_field: str = DEFAULT_TEACHER_RESPONSE_TOKEN_IDS_FIELD
    teacher_topk_storage_dtype: str = DEFAULT_TEACHER_TOPK_STORAGE_DTYPE
    lmbda: float | None = None
    sft_alpha: float | None = None
    seq_kd: bool = False
    offload_teacher_model: bool = False
    log_completions: bool = False
    swift_passthrough: dict[str, JsonValue] = Field(default_factory=dict)

    report_to: str | None = "wandb"
    wandb_project: str = "orbit"
    wandb_run_name: str = ""

    hf_backup_repo: str = ""
    backup_interval_minutes: int = 15

    def to_declared_dict(self) -> dict[str, JsonValue]:
        return self.model_dump(mode="json", exclude_unset=True)

    def to_effective_dict(self) -> dict[str, JsonValue]:
        payload = self.model_dump(mode="json")
        effective: dict[str, JsonValue] = {
            "model": payload["model"],
            "seed": payload["seed"],
            "dtype": payload["dtype"],
            "attn_impl": payload["attn_impl"],
            "train_type": payload["train_type"],
            "tuner_type": payload["tuner_type"],
            "learning_rate": payload["learning_rate"],
            "num_train_epochs": payload["num_train_epochs"],
            "per_device_train_batch_size": payload["per_device_train_batch_size"],
            "gradient_accumulation_steps": payload["gradient_accumulation_steps"],
            "warmup_ratio": payload["warmup_ratio"],
            "weight_decay": payload["weight_decay"],
            "max_grad_norm": payload["max_grad_norm"],
            "lr_scheduler_type": payload["lr_scheduler_type"],
            "max_length": payload["max_length"],
            "packing": payload["packing"],
            "dataset_num_proc": payload["dataset_num_proc"],
            "output_dir": payload["output_dir"],
            "save_steps": payload["save_steps"],
            "save_total_limit": payload["save_total_limit"],
            "logging_steps": payload["logging_steps"],
            "gradient_checkpointing": payload["gradient_checkpointing"],
            "use_hf": payload["use_hf"],
            "push_to_hub": payload["push_to_hub"],
            "num_gpus": payload["num_gpus"],
        }

        if self.model_type:
            effective["model_type"] = self.model_type
        if self.template:
            effective["template"] = self.template
        if self.deepspeed:
            effective["deepspeed"] = self.deepspeed

        if self.tuner_type == "lora":
            effective["lora_rank"] = self.lora_rank
            effective["lora_alpha"] = self.lora_alpha
            effective["lora_dropout"] = self.lora_dropout
            effective["target_modules"] = self.target_modules
            if self.quant_method:
                effective["quant_method"] = self.quant_method
                if self.quant_bits is not None:
                    effective["quant_bits"] = self.quant_bits

        if self.adapters:
            effective["adapters"] = list(self.adapters)
        if self.ref_adapters:
            effective["ref_adapters"] = list(self.ref_adapters)

        if self.push_to_hub and self.hub_model_id:
            effective["hub_model_id"] = self.hub_model_id

        if self.report_to:
            effective["report_to"] = self.report_to
            if self.report_to != "none":
                if self.wandb_project:
                    effective["wandb_project"] = self.wandb_project
                if self.wandb_run_name:
                    effective["wandb_run_name"] = self.wandb_run_name

        if self.train_type == "rlhf":
            effective["rlhf_type"] = self.rlhf_type
            if self.beta is not None:
                effective["beta"] = self.beta
            if self.reference_model:
                effective["reference_model"] = self.reference_model
            if self.rlhf_type in ("grpo", "ppo"):
                effective["max_completion_length"] = self.max_completion_length
            if self.rlhf_type == "grpo":
                effective["num_generations"] = self.num_generations
                if self.reward_funcs:
                    effective["reward_funcs"] = list(self.reward_funcs)
            if self.rlhf_type == "gkd":
                teacher_server = str(self.swift_passthrough.get("teacher_model_server", "")).strip()
                if self.teacher_data_mode != DEFAULT_TEACHER_DATA_MODE:
                    effective["teacher_data_mode"] = self.teacher_data_mode
                if self.teacher_data_mode == "offline_topk" or self.teacher_topk_indices_field != DEFAULT_TEACHER_TOPK_INDICES_FIELD:
                    effective["teacher_topk_indices_field"] = self.teacher_topk_indices_field
                if self.teacher_data_mode == "offline_topk" or self.teacher_topk_logprobs_field != DEFAULT_TEACHER_TOPK_LOGPROBS_FIELD:
                    effective["teacher_topk_logprobs_field"] = self.teacher_topk_logprobs_field
                if self.teacher_data_mode == "offline_topk" or self.teacher_response_token_ids_field != DEFAULT_TEACHER_RESPONSE_TOKEN_IDS_FIELD:
                    effective["teacher_response_token_ids_field"] = self.teacher_response_token_ids_field
                if self.teacher_data_mode == "offline_topk" or self.teacher_topk_storage_dtype != DEFAULT_TEACHER_TOPK_STORAGE_DTYPE:
                    effective["teacher_topk_storage_dtype"] = self.teacher_topk_storage_dtype
                if self.teacher_model and self.teacher_data_mode != "offline_topk":
                    effective["teacher_model"] = self.teacher_model
                if self.teacher_adapters and self.teacher_data_mode != "offline_topk":
                    effective["teacher_adapters"] = list(self.teacher_adapters)
                if self.teacher_model_type and self.teacher_data_mode != "offline_topk":
                    effective["teacher_model_type"] = self.teacher_model_type
                if self.teacher_model_revision and self.teacher_data_mode != "offline_topk":
                    effective["teacher_model_revision"] = self.teacher_model_revision
                if self.teacher_deepspeed and self.teacher_data_mode != "offline_topk":
                    effective["teacher_deepspeed"] = self.teacher_deepspeed
                if self.lmbda is not None:
                    effective["lmbda"] = self.lmbda
                if self.sft_alpha is not None:
                    effective["sft_alpha"] = self.sft_alpha
                effective["seq_kd"] = self.seq_kd
                effective["offload_teacher_model"] = self.offload_teacher_model
                effective["log_completions"] = self.log_completions
                if teacher_server and "teacher_model" not in effective:
                    effective.pop("teacher_model", None)

        if self.swift_passthrough:
            duplicate_keys = sorted(key for key in self.swift_passthrough if key in effective)
            if duplicate_keys:
                raise ValueError(
                    "swift_passthrough keys must not overlap modeled SwiftConfig fields: "
                    + ", ".join(duplicate_keys)
                )
            effective["swift_passthrough"] = dict(self.swift_passthrough)

        return effective

    def to_yaml_dict(self, dataset_path: str) -> dict:
        d: dict = {
            "model": self.model,
            "seed": self.seed,
            "torch_dtype": self.dtype,
            "attn_impl": self.attn_impl,
            "tuner_type": self.tuner_type,
            "dataset": [dataset_path],
            "max_length": self.max_length,
            "output_dir": self.output_dir,
            "use_hf": self.use_hf,
            "learning_rate": self.learning_rate,
            "num_train_epochs": self.num_train_epochs,
            "per_device_train_batch_size": self.per_device_train_batch_size,
            "gradient_accumulation_steps": self.gradient_accumulation_steps,
            "warmup_ratio": self.warmup_ratio,
            "weight_decay": self.weight_decay,
            "max_grad_norm": self.max_grad_norm,
            "lr_scheduler_type": self.lr_scheduler_type,
            "gradient_checkpointing": self.gradient_checkpointing,
            "save_steps": self.save_steps,
            "save_total_limit": self.save_total_limit,
            "logging_steps": self.logging_steps,
            "packing": self.packing,
            "dataset_num_proc": self.dataset_num_proc,
        }

        if self.model_type:
            d["model_type"] = self.model_type
        if self.template:
            d["template"] = self.template

        if self.tuner_type == "lora":
            d["lora_rank"] = self.lora_rank
            d["lora_alpha"] = self.lora_alpha
            d["lora_dropout"] = self.lora_dropout
            d["target_modules"] = self.target_modules

        # Full-parameter tuning cannot backprop through bnb/int quantized weights.
        # When callers leave quantization fields populated from a shared config
        # template, drop them from the emitted swift config for full training.
        if self.quant_method and self.tuner_type != "full":
            d["quant_method"] = self.quant_method
            if self.quant_bits is not None:
                d["quant_bits"] = self.quant_bits

        if self.deepspeed:
            d["deepspeed"] = self.deepspeed

        if self.train_type == "rlhf":
            d["rlhf_type"] = self.rlhf_type
            if self.beta is not None:
                d["beta"] = self.beta
            if self.reference_model:
                d["ref_model"] = self.reference_model
            if self.rlhf_type in ("grpo", "ppo"):
                d["max_completion_length"] = self.max_completion_length
            if self.rlhf_type == "grpo":
                d["num_generations"] = self.num_generations
                if self.reward_funcs:
                    d["reward_funcs"] = self.reward_funcs
            if self.rlhf_type == "gkd":
                if self.teacher_data_mode != DEFAULT_TEACHER_DATA_MODE:
                    d["teacher_data_mode"] = self.teacher_data_mode
                if self.teacher_data_mode == "offline_topk" or self.teacher_topk_indices_field != DEFAULT_TEACHER_TOPK_INDICES_FIELD:
                    d["teacher_topk_indices_field"] = self.teacher_topk_indices_field
                if self.teacher_data_mode == "offline_topk" or self.teacher_topk_logprobs_field != DEFAULT_TEACHER_TOPK_LOGPROBS_FIELD:
                    d["teacher_topk_logprobs_field"] = self.teacher_topk_logprobs_field
                if self.teacher_data_mode == "offline_topk" or self.teacher_response_token_ids_field != DEFAULT_TEACHER_RESPONSE_TOKEN_IDS_FIELD:
                    d["teacher_response_token_ids_field"] = self.teacher_response_token_ids_field
                if self.teacher_data_mode == "offline_topk" or self.teacher_topk_storage_dtype != DEFAULT_TEACHER_TOPK_STORAGE_DTYPE:
                    d["teacher_topk_storage_dtype"] = self.teacher_topk_storage_dtype
                if self.teacher_model and self.teacher_data_mode != "offline_topk":
                    d["teacher_model"] = self.teacher_model
                if self.teacher_adapters and self.teacher_data_mode != "offline_topk":
                    d["teacher_adapters"] = self.teacher_adapters
                if self.teacher_model_type and self.teacher_data_mode != "offline_topk":
                    d["teacher_model_type"] = self.teacher_model_type
                if self.teacher_model_revision and self.teacher_data_mode != "offline_topk":
                    d["teacher_model_revision"] = self.teacher_model_revision
                if self.teacher_deepspeed and self.teacher_data_mode != "offline_topk":
                    d["teacher_deepspeed"] = self.teacher_deepspeed
                if self.lmbda is not None:
                    d["lmbda"] = self.lmbda
                if self.sft_alpha is not None:
                    d["sft_alpha"] = self.sft_alpha
                d["seq_kd"] = self.seq_kd
                d["offload_teacher_model"] = self.offload_teacher_model
                d["log_completions"] = self.log_completions

        if self.adapters:
            d["adapters"] = self.adapters
        if self.ref_adapters:
            d["ref_adapters"] = self.ref_adapters

        if self.push_to_hub:
            d["push_to_hub"] = True
            if self.hub_model_id:
                d["hub_model_id"] = self.hub_model_id

        if self.report_to:
            d["report_to"] = self.report_to

        duplicate_keys = sorted(key for key in self.swift_passthrough if key in d)
        if duplicate_keys:
            raise ValueError(
                "swift_passthrough keys must not overlap modeled SwiftConfig fields: "
                + ", ".join(duplicate_keys)
            )
        d.update(self.swift_passthrough)

        return d

    def to_yaml(self, dataset_path: str) -> str:
        import yaml

        return yaml.dump(
            self.to_yaml_dict(dataset_path),
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

    def to_cli_args(self, dataset_path: str) -> list[str]:
        d = self.to_yaml_dict(dataset_path)
        args: list[str] = []
        for key, value in d.items():
            if isinstance(value, bool):
                args.extend([f"--{key}", str(value).lower()])
            elif isinstance(value, list):
                args.append(f"--{key}")
                for item in value:
                    args.append(str(item))
            else:
                args.extend([f"--{key}", str(value)])
        return args

    def swift_command(self, dataset_path: str) -> str:
        return f"swift {self.train_type} " + " ".join(self.to_cli_args(dataset_path))

    def swift_command_from_yaml(self, yaml_path: str) -> str:
        if self.num_gpus > 1:
            return f"NPROC_PER_NODE={self.num_gpus} swift {self.train_type} --config {yaml_path}"
        return f"swift {self.train_type} --config {yaml_path}"
