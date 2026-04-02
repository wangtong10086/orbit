# Running

## 运行前提

### 本地

建议使用项目已有环境：

```bash
source .venv-muzero/bin/activate
export PYTHONPATH=/home/ubuntu/affine-swarm
```

### Targon

真实运行优先在新租的隔离 H100/H200 上进行，不在本机长期跑训练。

需要：

- `TARGON_API_KEY`
- 已注册的新隔离 rental machine
- 远端可用的 Python 环境

## 典型流水线

### 1. 构建状态集

```bash
python -m projects.openspiel_muzero_pt.pipelines.build_state_corpus \
  --config projects/openspiel_muzero_pt/configs/othello_8x8.yaml \
  --output artifacts/openspiel_muzero_pt/othello_8x8/state_corpus.jsonl
```

产物：

- `state_corpus.jsonl`

### 2. 用 rollout MCTS 打 teacher label

```bash
python -m projects.openspiel_muzero_pt.pipelines.label_with_mcts \
  --config projects/openspiel_muzero_pt/configs/othello_8x8.yaml \
  --input artifacts/openspiel_muzero_pt/othello_8x8/state_corpus.jsonl \
  --output artifacts/openspiel_muzero_pt/othello_8x8/expert
```

产物：

- `expert_*.npz`
- `expert_*.json`

### 3. warm-start

```bash
python -m projects.openspiel_muzero_pt.pipelines.warmstart \
  --config projects/openspiel_muzero_pt/configs/othello_8x8.yaml \
  --expert artifacts/openspiel_muzero_pt/othello_8x8/expert \
  --out artifacts/openspiel_muzero_pt/othello_8x8/warmstart \
  --device cuda
```

关键产物：

- `warmstart/best.pt`
- `warmstart/last.pt`
- `warmstart/warmstart.progress.json`
- `warmstart/warmstart.quick_eval.json`

### 4. online training

```bash
python -m projects.openspiel_muzero_pt.pipelines.train_online \
  --config projects/openspiel_muzero_pt/configs/othello_8x8.yaml \
  --init artifacts/openspiel_muzero_pt/othello_8x8/warmstart/best.pt \
  --expert artifacts/openspiel_muzero_pt/othello_8x8/expert \
  --out artifacts/openspiel_muzero_pt/othello_8x8/online \
  --device cuda
```

关键产物：

- `online/online.progress.json`
- `online/online.events.jsonl`
- `online/latest.pt`
- `online/best.pt`
- `online/quick_eval.json`

### 5. 单独评测当前 checkpoint

```bash
python -m projects.openspiel_muzero_pt.pipelines.evaluate_vs_affine_mcts \
  --mode quick \
  --config projects/openspiel_muzero_pt/configs/othello_8x8.yaml \
  --checkpoint artifacts/openspiel_muzero_pt/othello_8x8/online/latest.pt \
  --games 64 \
  --device cuda \
  --output artifacts/openspiel_muzero_pt/othello_8x8/online/eval_quick.json
```

## Quick / Official 规则

- `quick`
  用于 warm-start 尾部 gate 和 online 周期评测。
- `official`
  用于最终正式验收。

当前策略：

- `quick < 90%` 时，不进入 `official`
- `official` 不应作为日常训练中的高频评测

## Targon 启动脚本

已有脚本：

- [`scripts/game/targon_muzero_othello.sh`](../../../scripts/game/targon_muzero_othello.sh)

示例：

```bash
bash scripts/game/targon_muzero_othello.sh --machine <registered-machine> --stage smoke
bash scripts/game/targon_muzero_othello.sh --machine <registered-machine> --stage full
```

## 关键运行指标

在线训练时，优先看：

- `online.progress.json`
  当前 step、replay_rows、selfplay_games_completed、loss
- `online.events.jsonl`
  actor chunk、train_log、quick_eval_submitted / complete
- `nvidia-smi`
  GPU util / memory
- `screen -ls`
  远端后台会话是否还活着

## 常见产物目录

推荐按变体组织：

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
