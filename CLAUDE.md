# Affine Forge — Universal Rules (auto-loaded every request)

## Loop Flow (MANDATORY)

1. `git pull --rebase`
2. Read: `PLAYBOOK.md`, `experiments/results.tsv`
3. Read relevant `knowledge/*.md` and `experiments/*.yaml` where status=running
4. Execute role work
5. Update: experiment YAML (if applicable), `knowledge/` (if new findings)
6. `git add <specific files>` → commit → `git pull --rebase` → push

## Git

- Commit: `{type}({scope}): {description}`
- **NEVER**: `git add -A`, `git add .`, `rm -rf`, `git push --force`, `git reset --hard`
- **NEVER** start background processes
- All committed content English. User-facing replies follow user's language.
- File > 500 lines → split

## Documentation Map

Each file has a single owner and purpose. **No duplication across files.**

| File | Purpose | Owner | Read by |
|------|---------|-------|---------|
| `CLAUDE.md` | Universal rules, constraints, architecture | Human | All agents (every loop) |
| `PLAYBOOK.md` | Strategy, priorities, current state | Strategist | All agents (every loop) |
| `experiments/results.tsv` | Training iteration history | Trainer | All agents |
| `experiments/*.yaml` | Individual experiment configs | Strategist designs, Trainer fills results | All agents |
| `knowledge/*.md` | Accumulated learnings by topic | Any agent | As needed |
| `knowledge/scoring.md` | Scoring algorithm analysis | Strategist | Strategist (every loop) |
| `knowledge/gap_analysis.md` | Quantitative position analysis | Strategist | All agents |
| `knowledge/environments/*.md` | Per-environment format, data, lessons | Data agent primarily | All agents |
| `prompts/strategist.md` | Strategist behavior + directives | Strategist (self-evolving) | Strategist only |
| `prompts/loop_main.md` | Trainer executor behavior | Trainer (self-evolving) | Trainer only |
| `prompts/data_synth.md` | Data agent behavior + rules | Data agent (self-evolving) | Data agent only |
| `synth_config.json` | Data status and inventory | Data agent | All agents |
| `docs/affine-system.md` | System architecture reference | Human | As needed (read-only) |
| `logs/data_synth_log.md` | Historical data synthesis log | Data agent | Archive only |

**Three-role architecture**:
- **Strategist**: thinks (WHAT + WHY). Designs experiments, owns gap analysis, approves training launches.
- **Trainer**: executes training (HOW to train). Follows experiment designs, runs eval, reports results.
- **Data Agent**: executes data work (HOW to get data). Generates/curates data, validates quality.

**Collaboration rules**:
- Strategist writes experiment YAML → Data prepares data → Strategist approves → Trainer executes
- All three communicate via adversarial sections in each other's prompt files
- `knowledge/` is shared append-friendly space
- Agent prompts are self-evolving: agents may update their own prompt files
- Environment specs live in `knowledge/environments/` — prompts should reference, not duplicate

---

## Project-Specific Rules

### Goal
Affine Leaderboard (Bittensor Subnet 120) **#1**. Iteratively train Qwen3-32B to win across all evaluation environments.

### Architecture

```
forge/                     # Python package (Click CLI: python3 -m forge)
  cli.py                   # CLI entry (score/data/compute/train/rental)
  config.py                # Centralized config (.env loading)
  compute/                 # GPU backends (targon.py serverless / ssh.py remote)
  data/                    # Data management (dynamo.py DDB / sft.py extraction / navworld_gen.py distill)
  training/                # Training (config.py script gen / runner.py orchestration)
  monitoring/              # Leaderboard monitoring
scripts/                   # Standalone scripts (eval_envs.py eval / game_gen.py GAME distill / liveweb_gen.py)
prompts/                   # Agent prompts (loop_main.md trainer / data_synth.md data agent)
PLAYBOOK.md                # Strategy, priorities, experiment protocol
experiments/               # Experiment tracking (YAML configs + results.tsv)
knowledge/                 # Accumulated learnings per topic
data/                      # Local data files (not committed)
```

**Adjacent projects** (read-only reference):
- `../affinetes/` — Eval environment source (ground truth for GAME/NAVWORLD/SWE-SYNTH I/O formats)
- `../liveweb-arena/` — LIVEWEB environment source
- `../affine-cortex/` — Leaderboard scoring algorithm

### Core Principles

1. **Geometric mean = weakest link kills** — leaderboard uses geometric mean across all envs
2. **Prepare before training** — each run ~$9, must: read eval source → audit data → fix all issues → checklist passes
3. **Eval-driven** — train → eval → diagnose → fix → next iteration
4. **Data quality > quantity** — format errors are worse than missing data
5. **Tooling > manual** — anything repeated 2+ times must become a CLI command

### Key Commands

```bash
python3 -m forge score --top 10                    # Leaderboard
forge rental status                                # GPU status
forge rental kill sglang|eval|training|all         # Kill processes
forge rental start-sglang <model> --tp 4           # Deploy inference
forge rental start-eval <model> --envs GAME,NAVWORLD --samples 100
forge data refresh                                 # DDB full refresh
forge data upload <file>                           # Upload to HF
forge train launch <dataset> --hf-repo <repo> --lr 1e-4 --lora-r 64
```

### Hard Constraints

- **Never deploy models** to Chutes or submit on-chain without user permission
- **HF repo must be private**
- **Never commit**: .env, secrets (IP/keys), .claude/ directory, data/ directory
- **Commit messages**: describe why not what, no Co-Authored-By, use `git add <specific files>`
- On blockers: don't retry in loops, switch approach or ask user
