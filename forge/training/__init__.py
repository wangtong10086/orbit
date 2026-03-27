"""Training pipeline: ms-swift based SFT/RLHF with PEFT and full parameter support.

Architecture:
    config.py       - SwiftConfig (ms-swift YAML/CLI generation)
    backend.py      - TrainBackend protocol
    sft.py          - SwiftBackend (unified SFT/RLHF backend)
    dpo_config.py   - Legacy DPO support (deprecated, use SwiftBackend)
    model.py        - Model merge/upload
    runner.py       - Orchestrator (SSH/Targon)
    checkpoint.py   - Checkpoint management
    executor/       - Compute executors (targon, remote)
"""
