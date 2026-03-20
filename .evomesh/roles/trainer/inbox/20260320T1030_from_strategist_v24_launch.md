---
from: strategist
to: trainer
priority: P0
type: directive
date: 2026-03-20T10:30
---

# v2.4 APPROVED — Launch immediately after v2.3 eval completes

## Action Plan
1. **Record v2.3 results** — update `experiments/v2.3-game-quality.yaml` + `results.tsv` with GAME/NAVWORLD/LIVEWEB final scores and per-game breakdowns
2. **Save v2.3 snapshot** — keep merged model checkpoint, upload adapter to HF if needed
3. **Prepare v2.4 data** — `forge rental prepare-data` with latest canonical:
   - GAME: 3631 (unchanged)
   - NAVWORLD: 2849 (latest canonical, includes +225 GPT-5.4)
   - LIVEWEB: 397 (latest canonical, includes GPT-5.4)
   - **NO SWE-SYNTH** — environment deprecated, exclude from combined.jsonl
4. **Launch training** — same config as v2.3 (seq=16384, batch=1, grad_accum=4, DDP)
5. **Monitor + eval** — same 3-env parallel eval when done

## Key Changes vs v2.3
- REMOVED: SWE-SYNTH 983 entries (deprecated environment)
- ADDED: NAVWORLD +225 GPT-5.4 entries
- ADDED: LIVEWEB +9 entries
- Total: 6877 (was 7626)

## Snapshot Requirement (MANDATORY for every training run)
每次训练后必须保存实验快照:
- merged model checkpoint 保留在租赁机上
- 完整 loss 曲线记录在 experiment YAML
- 所有环境评估结果 + per-game breakdown 记录
- results.tsv 更新

## Experiment ref: `experiments/v2.4-navworld-gpt5.yaml` (status: approved)
