---
name: muzero-game-training
description: "MuZero self-play RL training for board games (Othello, Clobber, Hex). Use when: launching game training, debugging win rate stagnation, tuning MuZero hyperparameters, analyzing training logs, setting up Targon H200 machines for game RL."
---

# MuZero Game Training Skill

## Architecture Overview

The MuZero training pipeline uses a single-GPU coordinator that time-shares between:
- **Inference** (MCTS self-play): multiple actor workers run parallel games, sending batched inference requests to the GPU
- **Training** (learner): consumes replay buffer + expert data, updates model weights

Code lives in `projects/openspiel_muzero_pt/`:
- `pipelines/train_online.py` — main online training loop
- `pipelines/selfplay_actor.py` — self-play actor processes
- `pipelines/learner.py` — loss computation & gradient updates
- `runtime/gpu_coordinator.py` — GPU time-sharing between inference and training
- `runtime/settings.py` — config parsing for actors, coordinator, online loop
- `configs/` — per-game YAML configs

## Supported Games

| Game | family | task_id | Board | Action space | Avg game length |
|------|--------|---------|-------|-------------|-----------------|
| Othello 8x8 | othello | 400000000 | 8x8 | 65 | ~60 moves |
| Clobber 5x6 | clobber | 700000000 | 5x6 | ~90 | ~17 moves |
| Hex 5x5 | hex | (varies) | 5x5 | 25 | ~13 moves |

## Training Phases

1. **Warmstart**: Supervised learning on expert-labeled positions (MCTS search targets)
2. **Online**: Self-play + training loop with ring replay buffer

## Key Lessons from Historical Training Runs

### Critical Issue: Self-play / Training Speed Imbalance

**This is the #1 problem.** When training consumes data much faster than self-play generates it, the model overfits massively on stale replay data.

Evidence from Othello V3 (2026-04-03):
- 310k steps × batch 2048 = 635M position-updates
- Self-play generated only 1.7M positions → each position trained **~370x**
- Loss **increased** from 2.1 to 2.7 (divergence)
- Win rate stagnated at 13-24%

Evidence from Clobber5 V5:
- 390k steps × batch 128 = 50M updates on 126k positions → each position trained **~400x**
- Win rate oscillated 14-26% with no improvement

### Root Cause: Batch Size Too Large

The GPU coordinator interleaves inference and training. A larger batch means the learner consumes more data per step, starving actors of inference time and creating a vicious cycle:
- Large batch → fast training → stale replay → overfitting
- Less inference time → slower self-play → even staler data

### Recommended Config Tuning

#### For H200 single-GPU (per game):

| Parameter | Too Aggressive | Balanced | Conservative |
|-----------|---------------|----------|-------------|
| `batch_size_per_gpu` | 2048 | 256-512 | 128 |
| `lr_online` | 5e-4 | 1e-4 — 2e-4 | 5e-5 |
| `max_train_microbatches_per_turn` | 2 | 1 | 1 |
| `live_capacity` (replay buffer) | 1M | 200k-500k | 100k |
| `actors.workers` | 12 | 8-12 | 4-6 |
| `train_num_simulations` | 128 | 32-64 | 16 |
| `snapshot_sync_interval` | 2000 | 100-200 | 50 |

#### Game-specific model sizing (current v2):

| Game | channels | repr_blocks | dyn_blocks | head_hidden | unroll | Notes |
|------|----------|------------|------------|-------------|--------|-------|
| Othello 8x8 | 96 | 6 | 2 | 192 | 3 | Kept for checkpoint compat |
| Clobber 5x6 | 128 | 10 | 4 | 256 | 3 | Kept for checkpoint compat |
| Hex 5x5 | 96 | 6 | 2 | 192 | 3 | (last known config) |

**Note**: Changing model architecture requires fresh warmstart — `load_checkpoint` uses strict `model.load_state_dict()`.

### Key Tuning Rules

1. **Self-play throughput > training throughput**: Target ~10-50 new positions per training step. If `replay_rows_delta_since_last_log = 0` at every log step, self-play is starved.
2. **Watch loss trend**: If loss increases for >50k steps, the model is diverging — reduce lr or batch size.
3. **Win rate plateau for 100k+ steps**: Change learning rate, increase model capacity, or restart from best checkpoint.
4. **Smaller replay buffer**: Forces model to train on fresher data. 200k is better than 1M for single-GPU.
5. **Lower simulations for self-play**: 32-64 sims generates games 2-4x faster than 128 sims. Quality is slightly lower but throughput gain dominates.
6. **Use bf16 precision**: Saves ~50% VRAM, allows larger model or more actors. No quality loss for these games.
7. **Snapshot sync ≤ 200**: Actors should get fresh weights frequently so self-play data matches current policy.

### Anti-patterns

- **fp32 with small model**: Wastes VRAM. Always use bf16 unless debugging NaN.
- **batch_size > 1024 on single GPU**: Training outpaces self-play 10-100x.
- **live_capacity = 1M with slow self-play**: Buffer fills late, then model trains on ancient data forever.
- **Restarting with latest.pt instead of best.pt**: Latest checkpoint may be worse due to oscillation.
- **Increasing actors without reducing train throughput**: More actors help only if GPU has inference time available.

## Machine Setup (Targon H200)

### SSH rental setup:
```bash
# 1. Create venv
uv venv /root/project/.venv-muzero --python 3.11
source /root/project/.venv-muzero/bin/activate
uv pip install torch==2.6.0+cu124 --index-url https://download.pytorch.org/whl/cu124
uv pip install numpy pyspiel pyyaml

# 2. Clone code
git clone <repo> /root/project
cd /root/project
export PYTHONPATH=/root/project

# 3. Run warmstart then online
python -m projects.openspiel_muzero_pt.pipelines.train_online \
  --config configs/<game>.yaml \
  --init <checkpoint.pt> \
  --expert <expert_dir> \
  --out <output_dir>/online \
  --device cuda
```

### Running two games on 2×H200:
Use `screen` sessions with `CUDA_VISIBLE_DEVICES`:
```bash
# GPU 0 — Game A
screen -dmS game-a bash -c '
  cd /root/project && . .venv-muzero/bin/activate
  export PYTHONPATH=/root/project CUDA_VISIBLE_DEVICES=0
  python -m projects.openspiel_muzero_pt.pipelines.train_online \
    --config <config_a.yaml> --init <ckpt_a.pt> --expert <expert_a> \
    --out <out_a>/online --device cuda \
    2>&1 | tee <out_a>/online.log
'

# GPU 1 — Game B
screen -dmS game-b bash -c '
  cd /root/project && . .venv-muzero/bin/activate
  export PYTHONPATH=/root/project CUDA_VISIBLE_DEVICES=1
  python -m projects.openspiel_muzero_pt.pipelines.train_online \
    --config <config_b.yaml> --init <ckpt_b.pt> --expert <expert_b> \
    --out <out_b>/online --device cuda \
    2>&1 | tee <out_b>/online.log
'
```

## Monitoring Training

### Key log fields:
- `train_log.step`: Current training step
- `train_log.loss`: Total loss (should decrease or stay stable, NOT increase)
- `train_log.last_eval_win_rate`: Win rate vs MCTS baseline (target: >50%)
- `train_log.replay_rows`: Total positions in replay buffer
- `train_log.selfplay_games_completed`: Total self-play games finished
- `train_log.replay_rows_delta_since_last_log`: New positions since last log (0 = self-play starved)

### Quick health check script:
```python
import json
with open("online.log") as f:
    for line in f:
        d = json.loads(line.strip())
        if d.get("kind") == "train_log" and d["step"] % 10000 == 0:
            print(f"step={d['step']} loss={d['loss']:.3f} wr={d['last_eval_win_rate']} "
                  f"games={d['selfplay_games_completed']} replay={d['replay_rows']} "
                  f"delta={d['replay_rows_delta_since_last_log']}")
```

## Historical Results Summary (2026-04-03)

| Run | Game | Steps | Best WR | Issue |
|-----|------|-------|---------|-------|
| othello_h200x2_online | Othello | 300k+ | 24% | Model too small (96ch), batch too large (2048), loss diverged |
| othello_fixed_v2 | Othello | 152k | 13% | Same config issues |
| clobber5_v1-v5 | Clobber | 50k-390k | 26% | Self-play too slow (4 actors), win rate plateau |
| hex5_concurrent | Hex5 | 40k | 32% | Short run, most promising game |

## V2 Optimizations (2026-04-03)

### Code Changes
1. **Cosine LR schedule with warmup** (`runtime/gpu_coordinator.py`):
   - Linear warmup for first `lr_warmup_steps` (default 1000)
   - Cosine decay to `lr_min_ratio × lr_online` over `learner_steps_online`
   - Config keys: `optimizer.lr_warmup_steps`, `optimizer.lr_min_ratio`

2. **Recency-weighted replay sampling** (`replay/ring_buffer.py`):
   - `recency_bias` parameter (0.0=uniform, 0.5=moderate recency, 1.0=strong recency)
   - Newer positions in ring buffer are sampled more frequently
   - Config key: `train.recency_bias`

3. **Expert ratio decay** (`pipelines/train_online.py`):
   - Start with configured expert ratio, decay linearly to `expert_min_ratio`
   - Duration: `expert_decay_steps` training steps
   - Config keys: `train.expert_decay_steps`, `train.expert_min_ratio`

### V2 Config Changes (both games)
| Parameter | V1 (old) | V2 (new) | Reason |
|-----------|----------|----------|--------|
| batch_size | 2048/128 | 256 | Prevent training outpacing self-play |
| lr_online | 5e-4 | 1.5e-4 | Reduce divergence risk |
| live_capacity | 1M/2M | 200k | Force fresher data |
| train_sims | 64/128 | 48 | Faster game generation |
| snapshot_sync | 200 | 100 | Fresher actor weights |
| microbatches_per_turn | 2 | 1 | More GPU time for inference |
| precision | fp32/bf16 | bf16 | Save VRAM everywhere |
| recency_bias | 0 | 0.5 | Sample newer data more |
| expert_decay_steps | 0 | 200k | Shift to self-play data over time |
| lr_warmup_steps | 0 | 1000 | Stable resume from checkpoint |
| lr_min_ratio | N/A | 0.1 | Cosine decay target |

### V2 Active Runs (started 2026-04-03)
- **Othello v2**: GPU0 on port 32526, init from `othello_v3_largerbuf/online/best.pt`, 96ch/6blk/2dyn
- **Clobber v2**: GPU1 on port 32526, init from `clobber5_h200x2_concurrent/online_v5/best.pt`, 128ch/10blk/4dyn
