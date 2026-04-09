"""Swift training backend — generates ms-swift commands from config.

Implements the TrainBackend protocol for both SFT and RLHF training
using ms-swift CLI (``swift sft`` / ``swift rlhf``).
"""

from __future__ import annotations

from orbit.integrations.ms_swift_offline_topk import validate_gkd_teacher_mode
from orbit.training.config import SwiftConfig


class SwiftBackend:
    """Unified ms-swift training backend for SFT and RLHF."""

    def generate_command(self, config: SwiftConfig, dataset_path: str) -> str:
        """Generate swift CLI command string."""
        return config.swift_command(dataset_path)

    def generate_yaml(self, config: SwiftConfig, dataset_path: str) -> str:
        """Generate YAML config for ms-swift."""
        return config.to_yaml(dataset_path)

    def validate_config(self, config: SwiftConfig) -> list[str]:
        """Validate config for swift training."""
        issues = []
        if config.learning_rate <= 0:
            issues.append(f"learning_rate must be positive, got {config.learning_rate}")
        if config.tuner_type == "lora" and config.lora_rank < 1:
            issues.append(f"lora_rank must be >= 1, got {config.lora_rank}")
        if config.max_length < 128:
            issues.append(f"max_length too small: {config.max_length}")
        if config.num_train_epochs < 1:
            issues.append(f"num_train_epochs must be >= 1, got {config.num_train_epochs}")
        if config.train_type not in ("sft", "rlhf", "pt"):
            issues.append(f"Invalid train_type: {config.train_type}")
        if config.train_type == "rlhf":
            valid_rlhf = {"dpo", "grpo", "kto", "cpo", "simpo", "orpo", "ppo", "gkd"}
            if config.rlhf_type not in valid_rlhf:
                issues.append(f"Invalid rlhf_type: {config.rlhf_type}")
        if config.tuner_type not in ("lora", "full"):
            issues.append(f"Invalid tuner_type: {config.tuner_type}")
        if config.tuner_type == "full" and config.quant_method is not None:
            issues.append("quant_method must be unset when tuner_type=full")
        if config.tuner_type == "full" and config.quant_bits is not None:
            issues.append("quant_bits must be unset when tuner_type=full")
        if config.train_type == "rlhf" and config.rlhf_type == "gkd":
            teacher_server = str(config.swift_passthrough.get("teacher_model_server", "")).strip()
            try:
                validate_gkd_teacher_mode(
                    teacher_data_mode=config.teacher_data_mode,
                    teacher_model=config.teacher_model,
                    teacher_model_server=teacher_server,
                    gkd_logits_topk=config.swift_passthrough.get("gkd_logits_topk"),
                    seq_kd=config.seq_kd,
                )
            except (ValueError, NotImplementedError) as exc:
                issues.append(str(exc))
        return issues
