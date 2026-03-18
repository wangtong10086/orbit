# Affine Swarm — Universal Rules (auto-loaded every request)

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
| `.evomesh/roles/*/ROLE.md` | Role-specific rules, adversarial sections | Each role + Strategist | Strategist reads all; others read own |
| `synth_config.json` | Data status and inventory | Data agent | All agents |
| `docs/affine-system.md` | System architecture reference | Human | As needed (read-only) |
| `logs/data_synth_log.md` | Historical data synthesis log | Data agent | Archive only |

**Three-role architecture**:
- **Strategist**: thinks (WHAT + WHY). Designs experiments, owns gap analysis, approves training launches.
- **Trainer**: executes training (HOW to train). Follows experiment designs, runs eval, reports results.
- **Data Agent**: executes data work (HOW to get data). Generates/curates data, validates quality.

**Collaboration rules**:
- Strategist writes experiment YAML → Data prepares data → Strategist approves → Trainer executes
- All three communicate via adversarial sections in each other's `.evomesh/roles/*/ROLE.md`
- `knowledge/` is shared append-friendly space
- Role ROLE.md files are self-evolving: agents may update their own ROLE.md
- Environment specs live in `knowledge/environments/` — ROLE.md should reference, not duplicate

## Communication Protocol

### Decision Flow
```
Strategist designs experiment (YAML) →
Data prepares/validates data →
Strategist approves launch (checks adversarial, checklist) →
Trainer executes training →
Trainer runs full eval (ALL environments, 100+ samples) →
Strategist analyzes results → next experiment
```

### Communication Channels (all via git)
1. `experiments/*.yaml` — Strategist writes plan, Trainer fills results
2. `synth_config.json` — Data writes status, Strategist/Trainer read
3. `knowledge/*.md` — shared learnings, anyone writes
4. `.evomesh/roles/*/ROLE.md` adversarial sections — cross-role challenges
5. `PLAYBOOK.md` — Strategist updates strategy, all read

### File Write Permissions
- Each role modifies **only their own** ROLE.md
- **Exception**: Strategist can write to ALL roles' ROLE.md (adversarial sections only)

| File | Strategist | Trainer | Data |
|------|------------|---------|------|
| Own ROLE.md | ✅ write | ✅ write | ✅ write |
| Other roles' ROLE.md | ✅ write (adversarial only) | ❌ | ❌ |
| `PLAYBOOK.md` | ✅ write | read | read |
| `experiments/*.yaml` | ✅ write (design) | ✅ write (results) | read |
| `synth_config.json` | read | read | ✅ write |
| `knowledge/*.md` | ✅ write | ✅ write | ✅ write |

### Adversarial Review (MANDATORY before training launch)
1. Strategist writes challenges into Trainer's and Data's ROLE.md adversarial sections
2. Trainer responds in own ROLE.md
3. Data responds in own ROLE.md
4. Strategist reads responses → approves or rejects in experiment YAML

### Pushback Protocol
- Data vetoes data mix → writes in own ROLE.md → Strategist must address
- Trainer pushes back on infeasible plan → writes in own ROLE.md → Strategist must redesign
- Strategist cannot override data quality concerns; executor roles cannot unilaterally change strategy

## Experiment Protocol

### One Variable Per Experiment
Each experiment changes exactly ONE thing. Document before training:
- **Variable**: what's changing
- **Hypothesis**: "Changing X should improve env Y score from A to B because Z"
- **Expected outcome**: quantitative prediction
- **Eval plan**: which environments, how many samples

### Method Switching Triggers
SFT is not the only option. Check every experiment cycle:
- **SFT plateau**: 2x data yields <15% improvement → escalate to DPO
- **Structural zero**: game/task at 0% across 3+ versions → flag as SFT-unlearnable
- **Rank stagnation**: rank unchanged for 3+ versions → method change needed

### Think in Ranks, Not Scores
Scoring uses decay_factor=0.5 — rank 2 gets half of rank 1's weight. Frame strategy in rank movements, not raw scores.

## Self-Evolution

Every 10 loops: self-audit own prompt file — delete dead rules, merge duplicates.
Quality gate: (a) what problem? cite metrics (b) what behavior changes? wording-only = skip (c) how to measure?
Log changes to evolution.log.

Agents may modify their own `.evomesh/roles/*/ROLE.md`. New learnings go to `knowledge/`, not into ROLE.md.

## Context Cleanup

If idle ≥10 loops or unable to process tasks: write final memory/short-term.md, then write `heartbeat.json`: `{"request": "restart", "reason": "context_cleanup", "loop": N}`. Server will restart your session with clean context. All file-based memory persists.

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
.evomesh/roles/            # Role definitions (ROLE.md + adversarial sections + memory)
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
