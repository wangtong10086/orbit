# Affine Forge Playbook

## Goal

Affine Leaderboard (Bittensor Subnet 120) **#1**.
Geometric mean across 6 environments. Weakest environment determines total score.

## Current State

- Ranking: ~#3 (2026-03-17)
- Model: Qwen3-32B QLoRA SFT (base → fine-tune)
- Latest: v11 training (15273 entries, NAVWORLD 3x boost)
- Weakest: NAVWORLD (5.1), LIVEWEB (not evaluated)
- Strongest: GAME (22.0), LGC-v2/PRINT (covered by SFT)

## Priority (by ROI)

1. **NAVWORLD data quality + quantity** — current biggest bottleneck, v11 has 3x data boost, awaiting eval
2. **Eval pipeline automation** — each manual eval cycle costs hours, need faster feedback
3. **DPO/RL exploration** — SFT may be hitting diminishing returns, DPO pipeline built but untested
4. **LIVEWEB data** — framework changing to standard tool calling, DashScope distillation failed (0%)
5. **SWE-SYNTH data** — cannot locally eval, need more high-score data from DDB

## Every Loop Must

1. `git pull --rebase` (get latest code and knowledge)
2. Read `PLAYBOOK.md` + `STATUS.md` + `experiments/results.tsv`
3. Read `experiments/*.yaml` where status=running (know what others are doing)
4. Read relevant `knowledge/*.md` (based on what you plan to do)
5. Check for duplicates (is someone already doing what you plan?)
6. Do your work
7. Update `STATUS.md` (what you're doing)
8. If experiment completed: update experiment YAML + results.tsv + knowledge/
9. `git add` → commit → `git pull --rebase` → resolve conflicts → push

## Hard Rules

- **Never deploy models** to Chutes or submit on-chain without human permission
- **HF repos must be private**
- **Never commit**: .env, secrets, .claude/ directory, data/ directory
- **Always train from base Qwen3-32B** — fine-tuning from other people's models doesn't converge (v1 experiment proved this)
- **Don't waste data on unlearnable games**: chess, go, checkers are unsolvable by SFT
- **NAVWORLD data must use apply_chat_template(tools=)** — text format "Call tool: xxx" is completely wrong
- **sglang needs --tool-call-parser qwen25** — without this, tool_calls field is always None
- **1 epoch is enough** — more epochs → overfitting, diminishing returns

## Experiment Protocol

Before starting any expensive operation (training, eval, distillation):
1. Create `experiments/{version}-{description}.yaml` with status=planned
2. Commit + push so others can see
3. Change status to running, do the work
4. On completion: fill in results, write learnings, update knowledge/
5. Update `experiments/results.tsv`

## Key Commands

```bash
python3 -m forge score --top 10                    # Leaderboard
forge rental status                                # GPU status
forge rental start-sglang <model> --tp 4           # Deploy inference
forge rental start-eval <model> --envs GAME,NAVWORLD
forge train launch <dataset> --hf-repo <repo> --lr 1e-4 --lora-r 64
forge data upload <file>                           # Upload to HF
```
