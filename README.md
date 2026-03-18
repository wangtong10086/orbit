# Affine Swarm

Multi-agent training system for [Affine Leaderboard](https://affine.io) (Bittensor Subnet 120). Iteratively fine-tune Qwen3-32B via QLoRA SFT to rank #1 across all evaluation environments.

## How It Works

```
Leaderboard observation → Data synthesis → Training → Evaluation → Diagnose → Repeat
```

The leaderboard uses **geometric mean** across 6 environments — any weak environment kills the total score. Our approach: build high-quality SFT data per environment, train with QLoRA, evaluate, and iterate.

## Environments

| Env | Type | Data Source | Our Score (v10) |
|-----|------|------------|-----------------|
| GAME | OpenSpiel strategy games | Bot strategies + DDB | 22.0 |
| NAVWORLD | Chinese travel planning (tool use) | Qwen3-max distillation + DDB | 5.1 |
| SWE-SYNTH | Code repair | DDB high-score samples | — |
| LIVEWEB | Browser agent | DDB filtered by length | — |
| LGC-v2 | Logic reasoning | DDB | — |
| PRINT | Program synthesis | DDB | — |

## Quick Start

```bash
# Setup
cp .env.example .env  # Fill in API keys (HF_TOKEN, AWS, AMAP, etc.)

# Leaderboard
python3 -m forge score --top 10

# Data
forge data refresh                                 # DDB full refresh
forge data upload <file>                           # Upload to HF

# Training
forge train launch <dataset> --hf-repo <repo> --lr 1e-4 --lora-r 64

# GPU management
forge rental status
forge rental start-sglang <model> --tp 4           # Deploy inference
forge rental start-eval <model> --envs GAME,NAVWORLD --samples 100
```

## Project Structure

```
forge/                     # Python CLI package (python3 -m forge)
  cli.py                   # CLI entry point
  compute/                 # GPU backends (Targon serverless / SSH remote)
  data/                    # Data management (DynamoDB / SFT extraction / distillation)
  training/                # Training script generation & orchestration
  monitoring/              # Leaderboard monitoring
scripts/                   # Standalone scripts (eval, game bots, data gen)
prompts/                   # Agent prompts (self-evolving)
  loop_main.md             # Training operator agent
  data_synth.md            # Data synthesis agent
experiments/               # Experiment tracking
  results.tsv              # Training iteration history (v1-v11)
knowledge/                 # Accumulated learnings
  environments/            # Per-environment format specs & lessons
  training.md              # Hyperparameter evolution & findings
  data.md                  # Data formats & DDB volumes
  infra.md                 # Infrastructure quirks & fixes
  failures.md              # Failure museum with costs
docs/
  affine-system.md         # System architecture reference (Affine/Affinetes/Targon/DDB)
PLAYBOOK.md                # Strategy & priorities
CLAUDE.md                  # Agent rules & documentation map
```

## Agent Workflow

Designed for [Claude Code](https://claude.com/claude-code) agents running in continuous loops:

1. `git pull --rebase`
2. Read `PLAYBOOK.md` + `experiments/results.tsv`
3. Read relevant `knowledge/*.md`
4. Execute work (train / synthesize data / evaluate)
5. Update `experiments/` and `knowledge/`
6. Commit + push

Three agent roles (defined in `.evomesh/roles/*/ROLE.md`):
- **Strategist** — experiment design, gap analysis, scoring optimization, launch approval
- **Trainer** — training execution, evaluation, infrastructure management
- **Data Agent** — data generation, DDB extraction, format validation, quality veto

All ROLE.md files are self-evolving: agents update their own rules as they learn.

## Training Config

```
Base model:  Qwen/Qwen3-32B (always from base, not from other fine-tunes)
Quantized:   unsloth/Qwen3-32B-bnb-4bit
Method:      QLoRA (4-bit NF4, LoRA r=64, alpha=128)
LR:          1e-4
Epochs:      1 (more = overfitting)
Packing:     True
Seq length:  4096
```

## Key Lessons (from knowledge/failures.md)

- **Read eval source code before training** — format mismatches are the #1 failure mode (~$30 wasted)
- **apply_chat_template is mandatory** for tool-calling data (NAVWORLD 0% → 8.7%)
- **sglang needs --tool-call-parser qwen25** — without it, tool_calls is always None
- **1 epoch is enough** — 3 epochs on 4528 samples risked catastrophic forgetting
- **Don't train from other fine-tunes** — QLoRA on deeply-tuned models causes loss oscillation

## License

Private repository.
