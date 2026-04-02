# OpenSpiel MuZero PT

PyTorch Gumbel MuZero stack for Affine OpenSpiel board games.

文档入口：

- [docs/README.md](./docs/README.md)
- [docs/architecture.md](./docs/architecture.md)
- [docs/running.md](./docs/running.md)
- [docs/development.md](./docs/development.md)
- [docs/adding_games.md](./docs/adding_games.md)

Current implementation scope:

- registered games: Othello 8x8, Hex 5/7/9/11, Clobber 5/6/7
- direct `pyspiel` runtime
- Python tree search
- expert warm-start
- centralized GPU coordinator for online self-play/training
- eval against current Affine baseline MCTS

## Package layout

- `games/`: registry, codecs, per-family state encoders, and OpenSpiel adapter
- `model/`: `BoardMuZeroNet`
- `search/`: Python tree search and Gumbel root logic
- `replay/`: expert shards and live replay buffers
- `runtime/`: online inference/training broker and runtime settings
- `pipelines/`: corpus build, labeling, warm-start, self-play, online train, eval

## Config conventions

The configs now separate concerns by ownership:

- `train`: learner hyperparameters and training cadence
- `actors`: CPU self-play worker parallelism
- `runtime.gpu_coordinator`: centralized GPU batching / snapshot sync settings
- `eval`: quick vs official evaluation policy
- `corpus` / `expert` / `buffers`: offline data and replay sizing

This split keeps future Hex / Clobber additions from mixing game-independent
runtime knobs back into model or training sections.

Available base configs:

- `configs/othello_8x8.yaml`
- `configs/hex_5.yaml`, `configs/hex_7.yaml`, `configs/hex_9.yaml`, `configs/hex_11.yaml`
- `configs/clobber_5.yaml`, `configs/clobber_6.yaml`, `configs/clobber_7.yaml`

## Recommended Reading

如果你是第一次接手这个子树，建议顺序：

1. 先读 [architecture.md](./docs/architecture.md)
2. 再读 [running.md](./docs/running.md)
3. 需要改代码时读 [development.md](./docs/development.md)
4. 需要扩游戏时读 [adding_games.md](./docs/adding_games.md)

## Targon-first runtime

Per current project constraints, real runtime validation should happen on a fresh
isolated Targon H100/H200 rental machine instead of the local workstation.

Prerequisites before running:

1. `TARGON_API_KEY` is configured for the local control machine.
2. A fresh isolated rental machine is provisioned and registered in `machines.json`.
3. The rental machine has Python and pip available.

Recommended launcher:

```bash
bash scripts/game/targon_muzero_othello.sh --machine <registered-machine> --stage smoke
```

Then the full vertical slice:

```bash
bash scripts/game/targon_muzero_othello.sh --machine <registered-machine> --stage full
```
