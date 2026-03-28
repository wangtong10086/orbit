"""Training pipeline: ms-swift based SFT/RLHF with PEFT and full parameter support.

Architecture:
    config.py       - SwiftConfig (ms-swift YAML/CLI generation)
    backend.py      - TrainBackend protocol
    sft.py          - SwiftBackend (unified SFT/RLHF backend)
    providers.py    - Explicit execution providers (SSH / Targon bootstrap / Targon image)
    ../pipeline/training.py - TrainingPipeline orchestration entrypoint
    dpo_config.py   - Legacy DPO support (deprecated, use SwiftBackend)
    model.py        - Model merge/upload
    runner.py       - Compatibility wrapper over TrainingPipeline
    checkpoint.py   - Checkpoint management
    executor/       - Compatibility shims over explicit providers
"""
