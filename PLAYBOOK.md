# Affine Forge Playbook

## Goal

Affine Leaderboard (Bittensor Subnet 120) **#1**.
Geometric mean across all environments. Weakest environment determines total score.

## Current State

- Ranking: Not deployed (fresh start from inherited data/knowledge)
- Model: Qwen3-32B QLoRA SFT (base → fine-tune)
- Inherited from old repo: 12,194 canonical entries across 7 environments
- Previous best (old repo v11): GAME 22.6, NAVWORLD 5.7
- New machine: awaiting user provision

## Strategic Assessment (inherited from 12 iterations)

### What works
- QLoRA lr=1e-4, r=64, alpha=128, 1 epoch — settled after 12 iterations
- Bot strategy data for GAME (gin_rummy 0%→100% immediately)
- apply_chat_template + sglang --tool-call-parser qwen25 for NAVWORLD
- Offline wheel bundle for Targon deployment reliability
- Packing=True for short-sample efficiency (GAME replies are 1-3 chars)

### What doesn't work
- Training from top model (loss oscillates, QLoRA unstable on fine-tunes)
- seq=4096 for SWE-SYNTH (98% truncated)
- DashScope for LIVEWEB distillation (0% success)
- Multiple epochs (overfitting on <15K samples)
- LR < 1e-4 for QLoRA (plateaus at loss ~0.45)

### Key bottlenecks
1. **NAVWORLD** — everyone is weak (7-34 pts), biggest differentiation ROI
2. **GAME weak games** — othello, hex, liars_dice always 0%, need specialized bots
3. **SWE-SYNTH** — needs seq=8192, cannot eval locally
4. **LIVEWEB** — data too long, upstream needs compression

## Priority (by ROI)

1. **First training run (v1)** — validate pipeline on new machine, use inherited data as-is
2. **Full evaluation** — establish baseline across all environments on new machine
3. **NAVWORLD expansion** — continue as biggest ROI (everyone weak = differentiation)
4. **GAME bot expansion** — add bots for othello/hex/liars_dice (currently 0%)
5. **DDB refresh** — data >24h stale, new high-score samples accumulating
6. **SWE-SYNTH seq=8192** — v12 approach, untested
7. **DPO exploration** — 2688 pairs ready, SFT may be hitting diminishing returns

## Every Loop Must

1. `git pull --rebase` (get latest code and knowledge)
2. Read `PLAYBOOK.md` + `experiments/results.tsv`
3. Read `experiments/*.yaml` where status=running (know what others are doing)
4. Read relevant `knowledge/*.md` (based on what you plan to do)
5. Check for duplicates (is someone already doing what you plan?)
6. Do your work
7. If experiment completed: update experiment YAML + results.tsv + knowledge/
9. `git add` → commit → `git pull --rebase` → resolve conflicts → push

## Hard Rules (Training-Specific)

Hard constraints on deployment/security/git are in `CLAUDE.md`. Below are training-specific rules:

- **Always train from base Qwen3-32B** — fine-tuning from other people's models doesn't converge (proven in iteration #1)
- **Don't waste data on unlearnable games**: chess, go, checkers are unsolvable by SFT
- **NAVWORLD data must use apply_chat_template(tools=)** — text format "Call tool: xxx" is completely wrong
- **sglang needs --tool-call-parser qwen25** — without this, tool_calls field is always None
- **1 epoch is enough** — more epochs → overfitting, diminishing returns
- **seq=8192 for SWE-SYNTH-heavy runs** — 98% of SWE-SYNTH truncated at 4096

## Experiment Protocol

Before starting any expensive operation (training, eval, distillation):
1. Create `experiments/{version}-{description}.yaml` with status=planned
2. Commit + push so others can see
3. Change status to running, do the work
4. On completion: fill in results, write learnings, update knowledge/
5. Update `experiments/results.tsv`

## Key Commands

See `CLAUDE.md` for full CLI reference. Most used:

```bash
python3 -m forge score --top 10                    # Leaderboard
forge rental status                                # GPU status
forge train launch <dataset> --hf-repo <repo>      # Train
```
