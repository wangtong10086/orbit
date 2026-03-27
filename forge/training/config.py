"""Training configuration for ms-swift based training.

Supports SFT and RLHF (DPO/GRPO/KTO/CPO/SimPO/ORPO/PPO) with
both PEFT (LoRA/QLoRA) and full parameter training via ms-swift CLI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TrainType(str, Enum):
    """Training method type."""
    SFT = "sft"
    RLHF = "rlhf"
    PT = "pt"


class RlhfType(str, Enum):
    """RLHF algorithm type."""
    DPO = "dpo"
    GRPO = "grpo"
    KTO = "kto"
    CPO = "cpo"
    SIMPO = "simpo"
    ORPO = "orpo"
    PPO = "ppo"
    GKD = "gkd"


class TunerType(str, Enum):
    """Parameter-efficient tuning type."""
    LORA = "lora"
    FULL = "full"


@dataclass
class SwiftConfig:
    """Configuration for ms-swift training runs.

    Generates YAML configs or CLI args for ``swift sft`` / ``swift rlhf``.
    Supports QLoRA, LoRA, and full parameter training.
    """

    # === Model ===
    model: str = "Qwen/Qwen3-32B"
    dtype: str = "bfloat16"
    attn_impl: str = "flash_attn"  # flash_attn, flash_attention_2, sdpa

    # === Training method ===
    train_type: str = "sft"    # sft, rlhf, pt
    rlhf_type: str = "dpo"    # dpo, grpo, kto, cpo, simpo, orpo, ppo, gkd

    # === Tuner ===
    tuner_type: str = "lora"   # lora, full
    lora_rank: int = 64
    lora_alpha: int = 128
    lora_dropout: float = 0.05
    target_modules: str = "all-linear"

    # === Quantization (QLoRA) ===
    quant_method: Optional[str] = "bnb"   # "bnb" for QLoRA, None for no quant
    quant_bits: Optional[int] = 4

    # === Training hyperparams ===
    learning_rate: float = 1e-4
    num_train_epochs: int = 1
    per_device_train_batch_size: int = 2
    gradient_accumulation_steps: int = 8
    warmup_ratio: float = 0.03
    weight_decay: float = 0.01
    max_grad_norm: float = 0.3
    lr_scheduler_type: str = "cosine"

    # === Data ===
    max_length: int = 4096
    packing: bool = True
    dataset_num_proc: int = 4

    # === Saving ===
    output_dir: str = "/root/checkpoints"
    save_steps: int = 100
    save_total_limit: int = 3
    logging_steps: int = 10

    # === Distributed ===
    deepspeed: Optional[str] = None      # zero2, zero3, zero2_offload, etc.
    gradient_checkpointing: bool = True

    # === HF integration ===
    use_hf: bool = True
    push_to_hub: bool = False
    hub_model_id: str = ""

    # === RLHF-specific ===
    beta: Optional[float] = None           # KL penalty coefficient
    max_completion_length: int = 512       # GRPO/PPO max gen length
    num_generations: int = 8               # GRPO: samples per prompt (G)
    reward_funcs: list[str] = field(default_factory=list)  # GRPO reward functions

    # === Adapters ===
    adapters: list[str] = field(default_factory=list)       # Resume / init
    ref_adapters: list[str] = field(default_factory=list)   # Reference model

    # === Multi-GPU ===
    num_gpus: int = 1  # NPROC_PER_NODE for distributed training

    # === Backup (forge-specific, not swift native) ===
    hf_backup_repo: str = ""
    backup_interval_minutes: int = 15

    def to_yaml_dict(self, dataset_path: str) -> dict:
        """Convert config to a dict suitable for swift YAML config.

        Args:
            dataset_path: Path to dataset file (local path on training machine)

        Returns:
            Dict that can be dumped to YAML for ``swift sft/rlhf config.yaml``
        """
        d: dict = {
            "model": self.model,
            "torch_dtype": self.dtype,
            "attn_impl": self.attn_impl,
            "tuner_type": self.tuner_type,
            "dataset": [dataset_path],
            "max_length": self.max_length,
            "output_dir": self.output_dir,
            "use_hf": self.use_hf,
            # Training hyperparams
            "learning_rate": self.learning_rate,
            "num_train_epochs": self.num_train_epochs,
            "per_device_train_batch_size": self.per_device_train_batch_size,
            "gradient_accumulation_steps": self.gradient_accumulation_steps,
            "warmup_ratio": self.warmup_ratio,
            "weight_decay": self.weight_decay,
            "max_grad_norm": self.max_grad_norm,
            "lr_scheduler_type": self.lr_scheduler_type,
            "gradient_checkpointing": self.gradient_checkpointing,
            # Saving
            "save_steps": self.save_steps,
            "save_total_limit": self.save_total_limit,
            "logging_steps": self.logging_steps,
            # Data
            "packing": self.packing,
            "dataset_num_proc": self.dataset_num_proc,
        }

        # LoRA params
        if self.tuner_type == "lora":
            d["lora_rank"] = self.lora_rank
            d["lora_alpha"] = self.lora_alpha
            d["lora_dropout"] = self.lora_dropout
            d["target_modules"] = self.target_modules

        # Quantization (QLoRA)
        if self.quant_method:
            d["quant_method"] = self.quant_method
            if self.quant_bits is not None:
                d["quant_bits"] = self.quant_bits

        # Distributed
        if self.deepspeed:
            d["deepspeed"] = self.deepspeed

        # RLHF-specific
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

        # Adapters
        if self.adapters:
            d["adapters"] = self.adapters
        if self.ref_adapters:
            d["ref_adapters"] = self.ref_adapters

        # Hub push
        if self.push_to_hub:
            d["push_to_hub"] = True
            if self.hub_model_id:
                d["hub_model_id"] = self.hub_model_id

        return d

    def to_yaml(self, dataset_path: str) -> str:
        """Generate YAML config string for ms-swift.

        Args:
            dataset_path: Path to dataset file

        Returns:
            YAML string for ``swift sft/rlhf``
        """
        import yaml
        return yaml.dump(
            self.to_yaml_dict(dataset_path),
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

    def to_cli_args(self, dataset_path: str) -> list[str]:
        """Generate CLI arguments for ms-swift command.

        Args:
            dataset_path: Path to dataset file

        Returns:
            List of CLI arguments (without the ``swift sft/rlhf`` prefix)
        """
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
        """Generate the full swift CLI command string.

        Args:
            dataset_path: Path to dataset file

        Returns:
            Complete command like ``swift sft --model ... --dataset ...``
        """
        subcmd = self.train_type  # sft, rlhf, or pt
        args = self.to_cli_args(dataset_path)
        return f"swift {subcmd} " + " ".join(args)

    def swift_command_from_yaml(self, yaml_path: str) -> str:
        """Generate swift command that reads from a YAML config.

        Args:
            yaml_path: Path to YAML config file

        Returns:
            Command like ``swift sft --config config.yaml`` or
            ``NPROC_PER_NODE=8 swift sft --config config.yaml`` for multi-GPU
        """
        subcmd = self.train_type
        if self.num_gpus > 1:
            return f"NPROC_PER_NODE={self.num_gpus} swift {subcmd} --config {yaml_path}"
        return f"swift {subcmd} --config {yaml_path}"


# Backward compatibility alias
TrainConfig = SwiftConfig
