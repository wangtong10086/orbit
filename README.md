# Affine Swarm

Multi-agent training system for [Affine Leaderboard](https://affine.io) (Bittensor Subnet 120). Iteratively fine-tune **Qwen3-32B** to rank #1 across all evaluation environments.

## Architecture Overview

Three-layer architecture with strict dependency isolation:

```
┌─────────────────────────────────────────────────────┐
│  Layer 2 — Agent                                    │
│  StrategistAgent · TrainerAgent · DataAgent          │
│  EvolutionLoop (sense → plan → act → reflect)       │
├─────────────────────────────────────────────────────┤
│  Layer 1 — Pipeline                                 │
│  DataPipeline · Evaluator · ExperimentTracker        │
├─────────────────────────────────────────────────────┤
│  Layer 0 — Foundation (zero cross-deps)             │
│  env/ (EnvHub + GEM + Sandbox)                      │
│  prompt/ (PromptBuilder + Templates)                │
│  training/ (SwiftConfig + Backend + Executor)       │
└─────────────────────────────────────────────────────┘
```

- **Layer 0** — standalone modules with no cross-dependencies (stdlib only)
- **Layer 1** — composable pipelines built on Layer 0
- **Layer 2** — autonomous agents orchestrating the full training loop

## Evaluation Environments

The leaderboard uses **geometric mean** across all environments — any zero kills the total score.

| Env | Type | Scoring Weight | Description |
|-----|------|:-:|-------------|
| GAME | OpenSpiel strategy games | 3.0 | 7 game types, multi-turn interaction |
| NAVWORLD | Travel planning (tool use) | 1.0 | Chinese travel, ≥3 tool calls required |
| SWE-SYNTH | Code repair | 1.0 | Software engineering bug fixing |
| LIVEWEB | Browser agent | 1.0 | Web navigation and interaction |
| LGC-v2 | Logic reasoning | 1.0 | Logic games, balanced think tags |
| PRINT | Program synthesis | 1.0 | Print output reasoning |

## Quick Start

```bash
# Setup
cp .env.example .env  # Fill in API keys (HF_TOKEN, AMAP, etc.)
pip install -e .

# Leaderboard
python3 -m forge score --top 10

# Data validation
forge data audit                                     # Validate all canonical files
forge data validate <file> --env NAVWORLD            # Deep quality audit
forge data ingest <file> --env ENV --source SRC      # Staging → canonical

# Training (ms-swift backend)
forge train launch data.jsonl --dataset-repo <repo> --train-type sft
forge train launch data.jsonl --dataset-repo <repo> --tuner-type full --no-quant --deepspeed zero3
forge train launch data.jsonl --dataset-repo <repo> --train-type rlhf --rlhf-type dpo

# GPU management
forge rental status
forge rental start-sglang <model> --tp 4
forge rental start-eval <model> --envs GAME,NAVWORLD --samples 100
```

## Project Structure

```
forge/
  cli.py                   # CLI entry point (python3 -m forge)
  cli_train.py             # Training subcommands
  cli_data.py              # Data management subcommands
  cli_rental.py            # GPU rental subcommands
  env/                     # [Layer 0] Environment definitions
    base.py                #   EnvProtocol, EnvSpec — data validation interface
    gem.py                 #   GemEnv, Observation, StepResult — interactive protocol
    sandbox.py             #   Sandbox, SandboxConfig — runtime lifecycle
    registry.py            #   EnvRegistry, EnvHub — dual registry
    game.py                #   GAME environment (data + GEM)
    navworld.py            #   NAVWORLD environment
    swe.py                 #   SWE-SYNTH environment
    liveweb.py             #   LIVEWEB environment
    lgc.py                 #   LGC-v2 environment
    print_env.py           #   PRINT environment
  prompt/                  # [Layer 0] Prompt engine
    builder.py             #   PromptBuilder — fluent message builder
    tools.py               #   Tool schema loader
    templates/             #   Per-env system prompts & tool schemas
  training/                # [Layer 0] Training backend
    config.py              #   SwiftConfig — all hyperparams
    backend.py             #   TrainBackend protocol
    sft.py                 #   SwiftBackend — ms-swift implementation
    model.py               #   LoRA merge & HF utilities
    executor/              #   Compute backends (Targon / SSH)
  pipeline/                # [Layer 1] Application pipelines
    data.py                #   DataPipeline — ingest → clean → validate → dedup
    eval.py                #   Evaluator — multi-env eval, geo mean
    experiment.py          #   ExperimentTracker — YAML experiment lifecycle
  agent/                   # [Layer 2] Autonomous agents
    base.py                #   AgentProtocol — sense → plan → act → reflect
    strategist.py          #   StrategistAgent — gap analysis, experiment design
    trainer.py             #   TrainerAgent — training & eval orchestration
    data_agent.py          #   DataAgent — data prep & quality audit
    loop.py                #   EvolutionLoop — full self-evolution cycle
  compute/                 # GPU backends (Targon / SSH)
  data/                    # Data utilities (canonical ops, SFT extraction)
  monitoring/              # Leaderboard monitoring
scripts/                   # Standalone scripts (eval, distillation, game bots)
experiments/               # Experiment YAML configs + results.tsv
knowledge/                 # Accumulated learnings by topic
  environments/            # Per-environment format specs & lessons
docs/                      # Architecture & system documentation
tests/                     # Unit tests for all layers
```

## Training Configuration

Training uses [ms-swift](https://github.com/modelscope/ms-swift) as the backend. Supported modes:

| Mode | CLI Flag | Description |
|------|----------|-------------|
| SFT + LoRA | `--train-type sft` (default) | QLoRA 4-bit, LoRA r=64, α=128 |
| SFT + Full | `--train-type sft --tuner-type full --no-quant` | Full parameter fine-tuning |
| DPO | `--train-type rlhf --rlhf-type dpo` | Direct Preference Optimization |
| GRPO | `--train-type rlhf --rlhf-type grpo` | Group Relative Policy Optimization |
| KTO/CPO/SimPO/ORPO/PPO | `--train-type rlhf --rlhf-type <type>` | Other RLHF algorithms |

Key training parameters:

```
Base model:    Qwen/Qwen3-32B
Backend:       ms-swift 4.x
DeepSpeed:     ZeRO-2 / ZeRO-3 (--deepspeed zero2|zero3)
Learning rate: 1e-4 (configurable via --lr)
Epochs:        1 (--epochs)
Seq length:    4096~32768 (--max-length)
Packing:       True
GPUs:          Multi-GPU via DeepSpeed
```

## Agent Workflow

Designed for AI agents running in continuous loops:

```
┌─ Strategist ─────────────────────────────────────┐
│  Gap analysis → Experiment design → Launch approval │
└───────────┬───────────────────────────┬───────────┘
            │ experiment YAML           │ experiment YAML
            ▼                           ▼
┌─ Data Agent ────────┐    ┌─ Trainer ──────────────┐
│  Data prep & audit  │    │  Training → Evaluation  │
│  Quality veto power │    │  Results → experiments/  │
└─────────────────────┘    └─────────────────────────┘
```

Three agent roles (defined in `.evomesh/roles/*/ROLE.md`):
- **Strategist** — gap analysis, experiment design, scoring optimization, launch approval
- **Trainer** — training execution, evaluation, infrastructure management
- **Data Agent** — data generation, format validation, quality veto

Communication via git-committed files: experiment YAML, knowledge/, ROLE.md adversarial sections.

## Key Lessons

- **Read eval source code before training** — format mismatches are the #1 failure mode
- **apply_chat_template is mandatory** for tool-calling data (NAVWORLD 0% → 8.7%)
- **1 epoch is enough** — more epochs risk catastrophic forgetting
- **Geometric mean = weakest link kills** — every environment must score > 0
- **Full SFT + DeepSpeed ZeRO-3** — enables training without quantization on 8×H200

## License

Private repository.
