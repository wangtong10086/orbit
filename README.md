# Affine Swarm

Multi-agent training system for [Affine Leaderboard](https://affine.io) (Bittensor Subnet 120). Iteratively fine-tune Qwen3-32B via QLoRA SFT to rank #1 across all evaluation environments.

## How It Works

```
Leaderboard observation → Data synthesis → Training → Evaluation → Diagnose → Repeat
```

The leaderboard uses **geometric mean** across 6 environments — any weak environment kills the total score. Our approach: build high-quality SFT data per environment, train with QLoRA, evaluate, and iterate.

## Environments

| Env | Type | Data Source | Status |
|-----|------|------------|--------|
| GAME | OpenSpiel strategy games | Bot strategies + historical samples | Training |
| NAVWORLD | Chinese travel planning (tool use) | Claude Sonnet distillation + QQR filtering | Training |
| SWE-SYNTH | Code repair | Historical high-score samples (cleaned) | Training |
| LIVEWEB | Browser agent | Claude/GPT distillation pipeline + historical | Training |
| LGC-v2 | Logic reasoning | Excluded (user directive) | — |
| PRINT | Program synthesis | Excluded (user directive) | — |

## Quick Start

```bash
# Setup
cp .env.example .env  # Fill in API keys (HF_TOKEN, AMAP, etc.)

# Leaderboard
python3 -m forge score --top 10

# Data
forge data audit                                   # Validate canonical files
forge data ingest <file> --env ENV --source SRC    # Staging → canonical
forge data canonical-upload --env all              # Sync to HF
forge data build-training -o /tmp/combined.jsonl   # Build training mix
forge data build-training -m m3                    # Build + upload to machine

# LIVEWEB data generation (teacher bot)
forge data liveweb-gen --seeds 1-2500 -o data/lw.jsonl           # Generate locally
forge data liveweb-gen --seeds 1-2500 --ingest                   # Generate + canonical + HF
forge data liveweb-gen --seeds 1-100 -m m1                       # Run on remote machine
forge data liveweb-gen --seeds 1-10 --dry-run                    # Show plan only

# NAVWORLD data generation
forge data navworld-gen -n 50 --type half_day -o data/nw.jsonl   # Single type
forge data navworld-gen -n 50 --phase1                           # All 8 types

# Training
forge train launch <dataset> --hf-repo <repo> --lr 1e-4 --lora-r 64

# Remote machine operations
forge remote -m m1 status                          # GPU/process status
forge remote -m m1 exec "nvidia-smi"               # Run command
forge remote -m m1 upload <local> <remote>         # Upload file

# Targon machine lifecycle
forge rental provision --gpu H200                  # Rent machine
forge rental list                                  # List rentals
```

## Project Structure

```
forge/                     # Python CLI package (python3 -m forge)
  cli.py                   # CLI entry point
  compute/                 # GPU backends (Targon serverless / SSH remote)
  data/                    # Data management (canonical ops / SFT extraction / distillation)
  training/                # Training script generation & orchestration
  monitoring/              # Leaderboard monitoring
scripts/                   # Standalone scripts (eval, game bots, liveweb gen)
.evomesh/roles/            # Agent role definitions (ROLE.md + memory + inbox)
experiments/               # Experiment tracking (YAML configs + results.tsv)
knowledge/                 # Accumulated learnings
  environments/            # Per-environment format specs & lessons
  training.md              # Hyperparameter evolution & findings
  data.md                  # Data formats & generation methods
  infra.md                 # Infrastructure quirks & fixes
  failures.md              # Failure museum with costs
docs/
  affine-system.md         # System architecture reference
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
- **Data Agent** — data generation, format validation, quality veto, pipeline development

All ROLE.md files are self-evolving: agents update their own rules as they learn.

## Training Config

```
Base model:  Qwen/Qwen3-32B (always from base, not from other fine-tunes)
Quantized:   unsloth/Qwen3-32B-bnb-4bit
Method:      QLoRA (4-bit NF4, LoRA r=64, alpha=128)
LR:          1e-4
Epochs:      1 (more = overfitting)
Packing:     True
Seq length:  16384
GPUs:        All available (DDP)
```

## Key Lessons (from knowledge/failures.md)

- **Read eval source code before training** — format mismatches are the #1 failure mode (~$30 wasted)
- **apply_chat_template is mandatory** for tool-calling data (NAVWORLD 0% → 8.7%)
- **sglang needs --tool-call-parser qwen25** — without it, tool_calls is always None
- **1 epoch is enough** — 3 epochs on 4528 samples risked catastrophic forgetting
- **Don't train from other fine-tunes** — QLoRA on deeply-tuned models causes loss oscillation

## License

Private repository.
