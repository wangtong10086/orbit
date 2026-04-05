"""Training configuration for ms-swift based training."""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from forge.foundation.schema import StrictModel


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


class SwiftConfig(StrictModel):
    """Configuration for ms-swift training runs."""

    model: str = "Qwen/Qwen3-32B"
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

    report_to: str | None = "wandb"
    wandb_project: str = "affine-forge"
    wandb_run_name: str = ""

    hf_backup_repo: str = ""
    backup_interval_minutes: int = 15

    def to_yaml_dict(self, dataset_path: str) -> dict:
        d: dict = {
            "model": self.model,
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
            if self.rlhf_type in ("grpo", "ppo"):
                d["max_completion_length"] = self.max_completion_length
            if self.rlhf_type == "grpo":
                d["num_generations"] = self.num_generations
                if self.reward_funcs:
                    d["reward_funcs"] = self.reward_funcs

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
            if self.wandb_project:
                d["wandb_project"] = self.wandb_project
            if self.wandb_run_name:
                d["wandb_run_name"] = self.wandb_run_name

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
