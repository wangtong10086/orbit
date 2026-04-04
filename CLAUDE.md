# Affine Swarm — Universal Rules (auto-loaded every request)

Legacy multi-agent workflow notes. This file is retained for historical context only and is not the current source of truth for architecture, CLI, or refactor state.

Use these files as the current authority instead:

- `README.md`
- `docs/README.md`
- `docs/refactor/README.md`

The remainder of this file is archived legacy guidance. It may conflict with current code, docs, and refactor governance, so do not use it as an active instruction source.

Historical note: the legacy `knowledge/` directory referenced in older workflow
examples was retired on 2026-04-04. Promote any still-relevant material into
`docs/` or `docs/refactor/` instead of recreating that archive tree.

## Loop Flow (MANDATORY)

1. **Strategist only**: `git pull --rebase`. Worker roles skip this step.
2. Read: `PLAYBOOK.md`, `experiments/results.tsv`
3. Read relevant `docs/*.md`, `docs/refactor/*.md`, and `experiments/*.yaml` where status=running
4. Execute role work
5. Update: experiment YAML and active docs when new findings change current guidance
6. `git add <specific files>` → commit → push. Strategist: `git pull --rebase` before push. Workers: push directly (do NOT pull/stash/rebase — if push fails due to conflict, skip this push and retry next loop).

## Git

- Commit: `{type}({scope}): {description}`
- **NEVER**: `git add -A`, `git add .`, `rm -rf`, `git push --force`, `git reset --hard`, `git checkout -- .`, `git restore .`, `git stash`
- **NEVER discard or commit other roles' uncommitted changes**: If `git status` shows unstaged modifications/deletions you did NOT make, leave them alone. Other roles may be mid-development. Only `git add` and commit files YOU created or modified. If unstaged changes block `git pull --rebase`, skip the pull this loop — do NOT commit, stash, checkout, or discard other roles' work to unblock it.
- **Git pull only by Strategist**: Only the Strategist runs `git pull --rebase`. Workers do NOT pull — they read files directly from the working tree. This prevents workers from running stash/checkout/restore to resolve conflicts, which can destroy other roles' uncommitted work.
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
| `docs/*.md` / `docs/refactor/*.md` | Current docs and refactor archive | Human | As needed |
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
- Strategist writes directives/challenges into Trainer's and Data's ROLE.md adversarial sections
- Trainer/Data respond in their own ROLE.md; Strategist reads their responses
- Role ROLE.md files are self-evolving: agents may update their own ROLE.md
- Promote reusable environment notes into `docs/` instead of reviving ad hoc archive trees

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
3. `docs/*.md` / `docs/refactor/*.md` — maintained docs, updated intentionally
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

Agents may modify their own `.evomesh/roles/*/ROLE.md`. New learnings that affect current behavior belong in the active docs set, not in ROLE.md.

### ROLE.md File Hygiene (MANDATORY)
- **ROLE.md ≤ 150 lines**. If exceeding → immediately archive completed adversarial items to `memory/short-term.md`
- **Adversarial sections**: only ACTIVE items (current directives, unresolved challenges). Completed → archive.
- **Task tracking**: active tasks go in `todo.md`, not ROLE.md
- **Historical logs**: go in `memory/short-term.md`, not ROLE.md
- ROLE.md contains: mission, rules, boundaries, scope, and ACTIVE adversarial items only

## Context Cleanup

If idle ≥1 loop or unable to process tasks: write final memory/short-term.md, then write `heartbeat.json`: `{"request": "restart", "reason": "context_cleanup", "loop": N}`. Server will restart your session with clean context. All file-based memory persists.

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
  data/                    # Data management (canonical_ops.py ops / sft.py extraction / navworld_gen.py distill)
  training/                # Training (config.py script gen / runner.py orchestration)
  monitoring/              # Leaderboard monitoring
scripts/                   # Standalone scripts (eval_envs.py eval / game_gen.py GAME distill / liveweb_gen.py)
.evomesh/roles/            # Role definitions (ROLE.md + adversarial sections + memory)
PLAYBOOK.md                # Strategy, priorities, experiment protocol
experiments/               # Experiment tracking (YAML configs + results.tsv)
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
forge data audit                                   # Validate all canonical files
forge data ingest <file> --env ENV --source SRC    # Staging → canonical (validate+dedup+HF)
forge data canonical-upload --env all              # Sync canonical → HF
forge data navworld-gen -n 50 --type half_day      # Generate NAVWORLD data by type
forge data navworld-gen -n 50 --phase1             # All 8 Phase 1 diversity types
forge data analyze <file>                          # Analyze dataset stats
forge data validate <file>                         # Deep quality audit
forge data upload <file>                           # Upload any file to HF
forge train launch <dataset> --hf-repo <repo> --lr 1e-4 --lora-r 64
```

### Hard Constraints

- **Never deploy models** to Chutes or submit on-chain without user permission
- **HF repo must be private**
- **Never commit**: .env, secrets (IP/keys), .claude/ directory, data/ directory
- **Commit messages**: describe why not what, no Co-Authored-By, use `git add <specific files>`
- On blockers: don't retry in loops, switch approach or ask user
