"""Training pipeline: ms-swift based SFT/RLHF with PEFT and full parameter support.

Architecture:
    config.py       - SwiftConfig (ms-swift YAML/CLI generation)
    backend.py      - TrainBackend protocol
    sft.py          - SwiftBackend (unified SFT/RLHF backend)
    ../pipeline/training.py - Control-side training pipeline over execution bundles and runtimes
    dpo_config.py   - DPO script generation helpers
    model.py        - Model merge/upload
    checkpoint.py   - Checkpoint management
"""
