# Running

## Prerequisites

### Local

Recommended environment:

```bash
source .venv-muzero/bin/activate
export PYTHONPATH=/home/ubuntu/affine-swarm
```

### Targon

Real runs should happen on a freshly rented isolated H100/H200 machine, not on the local workstation.

Requirements:

- `TARGON_API_KEY`
- A newly registered isolated rental machine
- A usable Python environment on the remote host

## Typical Pipeline

### 1. Build a State Corpus

```bash
python -m projects.openspiel_muzero_pt.pipelines.build_state_corpus \
  --config projects/openspiel_muzero_pt/configs/othello_8x8.yaml \
  --output artifacts/openspiel_muzero_pt/othello_8x8/state_corpus.jsonl
```

Artifacts:

- `state_corpus.jsonl`

### 2. Label the Corpus with Rollout MCTS

```bash
python -m projects.openspiel_muzero_pt.pipelines.label_with_mcts \
  --config projects/openspiel_muzero_pt/configs/othello_8x8.yaml \
  --input artifacts/openspiel_muzero_pt/othello_8x8/state_corpus.jsonl \
  --output artifacts/openspiel_muzero_pt/othello_8x8/expert
```

Artifacts:

- `expert_*.npz`
- `expert_*.json`

### 3. Warm-start

```bash
python -m projects.openspiel_muzero_pt.pipelines.warmstart \
  --config projects/openspiel_muzero_pt/configs/othello_8x8.yaml \
  --expert artifacts/openspiel_muzero_pt/othello_8x8/expert \
  --out artifacts/openspiel_muzero_pt/othello_8x8/warmstart \
  --device cuda
```

Key artifacts:

- `warmstart/best.pt`
- `warmstart/last.pt`
- `warmstart/warmstart.progress.json`
- `warmstart/warmstart.quick_eval.json`

### 4. Online Training

```bash
python -m projects.openspiel_muzero_pt.pipelines.train_online \
  --config projects/openspiel_muzero_pt/configs/othello_8x8.yaml \
  --init artifacts/openspiel_muzero_pt/othello_8x8/warmstart/best.pt \
  --expert artifacts/openspiel_muzero_pt/othello_8x8/expert \
  --out artifacts/openspiel_muzero_pt/othello_8x8/online \
  --device cuda
```

Key artifacts:

- `online/online.progress.json`
- `online/online.events.jsonl`
- `online/latest.pt`
- `online/best.pt`
- `online/quick_eval.json`

### 5. Evaluate a Checkpoint Directly

```bash
python -m projects.openspiel_muzero_pt.pipelines.evaluate_vs_affine_mcts \
  --mode quick \
  --config projects/openspiel_muzero_pt/configs/othello_8x8.yaml \
  --checkpoint artifacts/openspiel_muzero_pt/othello_8x8/online/latest.pt \
  --games 64 \
  --device cuda \
  --output artifacts/openspiel_muzero_pt/othello_8x8/online/eval_quick.json
```

## Quick / Official Rules

- `quick`
  Used for the warm-start tail gate and periodic online evaluation.
- `official`
  Used for final formal acceptance.

Current policy:

- Do not enter `official` while `quick < 90%`
- `official` should not be used as a high-frequency daily evaluation loop

## Targon Launcher

Existing script:

- [`scripts/game/targon_muzero_othello.sh`](../../../scripts/game/targon_muzero_othello.sh)

Examples:

```bash
bash scripts/game/targon_muzero_othello.sh --machine <registered-machine> --stage smoke
bash scripts/game/targon_muzero_othello.sh --machine <registered-machine> --stage full
```

## Key Runtime Signals

For online training, check these first:

- `online.progress.json`
  Current step, replay rows, self-play games completed, and loss
- `online.events.jsonl`
  Actor chunks, train logs, and quick-eval submit / complete events
- `nvidia-smi`
  GPU utilization and memory
- `screen -ls`
  Whether the remote background session is still alive

## Common Artifact Layout

Recommended variant-based layout:

```text
artifacts/openspiel_muzero_pt/
  othello_8x8/
  hex_5/
  hex_7/
  hex_9/
  hex_11/
  clobber_5/
  clobber_6/
  clobber_7/
```
