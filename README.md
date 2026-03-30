# Affine Swarm

Multi-agent training system for [Affine Leaderboard](https://affine.io) (Bittensor Subnet 120). Iteratively fine-tune Qwen3-32B via QLoRA SFT to rank #1 across all evaluation environments.

## How It Works

```
Leaderboard observation → Data synthesis → Training → Evaluation → Diagnose → Repeat
```

The leaderboard uses **geometric mean** across 6 environments — any weak environment kills the total score. Our approach: build high-quality SFT data per environment, train with QLoRA, evaluate, and iterate.

## Environments

| Env | Type | Data Source | Count | Status |
|-----|------|------------|-------|--------|
| GAME | OpenSpiel strategy games | MCTS bot vs random | 47000 | Training |
| NAVWORLD | Chinese travel planning (tool use) | GPT-5.4 distillation + QQR filtering | 10782+ | Training |
| SWE-INFINITE | Code repair (GitHub PRs) | GPT-5.4 distillation | 1600+ | Training |
| LIVEWEB | Browser agent | GPT-5.4 teacher bot | 17108 | Training |
| MEMORYGYM | Memory management | Hybrid generation | 20000 | Training |
| LGC-v2 | Logic reasoning | Excluded (user directive) | — | — |
| PRINT | Program synthesis | Excluded (user directive) | — | — |

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

# NAVWORLD data generation (7 eval types: intercity, multiday, hybrid, food_tour, business, single_poi, family_study)
forge data navworld-gen -n 100 --model gpt-5.4 --type intercity -o data/nw_intercity.jsonl
forge data navworld-gen -n 100 --model gpt-5.4 --type single_poi -o data/nw_single_poi.jsonl
forge data navworld-gen -n 50 --phase1                           # All diversity types (including non-eval)

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
Method:      Full fine-tuning (ms-swift or TRL SFTTrainer)
LR:          2e-5
Epochs:      1 (more = overfitting)
Seq length:  32768
GPUs:        8x H200 (DeepSpeed ZeRO-3)
Checkpoint:  ~12% training optimal (v2.28 ckpt600)
```

## Key Lessons

- **Read eval source code before training** — format mismatches are the #1 failure mode
- **tools field required in training data** — ms-swift needs it for proper tool_call tokenization
- **sglang needs --tool-call-parser qwen25** — without it, tool_calls is always None
- **1 epoch, early checkpoint** — v2.28 optimal at ~12% training (ckpt600/5000)
- **NW data ratio matters** — 19.7% → NW 42.34; 6.5% → NW 44.08 (more total data compensates)
- **QQR code scoring for quality filter** — local scorer catches budget/tips/IC gaps before training

## License

Private repository.
