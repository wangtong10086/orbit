# Affine Forge — Universal Rules (auto-loaded every request)

## Loop Flow (MANDATORY)

1. `git pull --rebase`
2. **`cat` and read**: ROLE.md, inbox/*, memory/short-term.md (EVERY loop, do NOT rely on memory)
   Also read (every 5 loops or when notified): blueprint.md, status.md, shared/decisions.md
3. Process inbox (P0 immediately, P1 within 2 loops) → move to inbox/processed/
4. Execute role work
5. Write outputs (ALL mandatory, do in one step):
   - `memory/short-term.md` — Done / Blockers / In-progress / Next focus
   - `metrics.log` — append CSV: `timestamp,duration_s,tasks_done,errors,inbox_processed`
   - `heartbeat.json` — write `{"ts": <unix_ms>}` (server uses this to detect brain-dead roles)
   - `todo.md` — mark completed, add new
6. `git add <own files only>` → commit → `git pull --rebase` → push

Idle? Write "No tasks, idle". 3× idle → light mode (inbox + memory/metrics only).

## Git

- Commit: `{type}({scope}/{role}): {description}`
- **NEVER**: `git add -A`, `git add .`, `rm -rf`, `git push --force`, `git reset --hard`
- **NEVER** start background processes
- All committed content English. User-facing replies follow user's language.
- File > 500 lines → split

## Communication

- Inbox: `YYYYMMDDTHHMM_from_topic.md`, frontmatter: from/to/priority/type/date
- P0/P1 done → `type: ack, status: done` to sender
- Cross-role: trainer directs data role. Both use adversarial review sections in ROLE.md for mutual audit.

## Shared Docs

- shared/decisions.md: append-only
- project.yaml: ⚠️ Server reads this to discover roles — only Central AI may write.

## Self-Evolution

Every 10 loops: self-audit ROLE.md — delete dead rules, merge duplicates.
Quality gate: (a) what problem? cite metrics (b) what behavior changes? wording-only = skip (c) how to measure?
Log changes to evolution.log.

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
logs/                      # Iteration logs (iteration_log.md full history)
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
