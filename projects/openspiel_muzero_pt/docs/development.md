# Development

## Development Goals

This subtree prioritizes three things:

1. Correct mathematical semantics
2. Verifiable real execution paths
3. Minimal changes to the runtime / search trunk when adding games

## Local Development Environment

Recommended environments:

- `./.venv-muzero`
  For tests and local smoke runs
- `./.venv-all`
  For compile checks and helper scripts

Common setup:

```bash
source .venv-muzero/bin/activate
export PYTHONPATH=/home/ubuntu/affine-swarm
```

## Test Commands

Full regression:

```bash
./.venv-muzero/bin/python -m pytest -q projects/openspiel_muzero_pt/tests
```

Static compile check:

```bash
./.venv-all/bin/python -m compileall projects/openspiel_muzero_pt
```

## Suggested Reading Order Before Changing Code

### Changing Game Representation

Read first:

- [`games/game_spec.py`](../games/game_spec.py)
- [`games/affine_registry.py`](../games/affine_registry.py)
- [`games/action_codecs.py`](../games/action_codecs.py)
- [`games/encoders.py`](../games/encoders.py)
- [`games/adapters.py`](../games/adapters.py)

### Changing Search

Read first:

- [`search/tree.py`](../search/tree.py)
- [`search/puct.py`](../search/puct.py)
- [`search/gumbel_root.py`](../search/gumbel_root.py)
- [`search/batched_search.py`](../search/batched_search.py)

### Changing the Online Runtime

Read first:

- [`runtime/inference.py`](../runtime/inference.py)
- [`runtime/gpu_coordinator.py`](../runtime/gpu_coordinator.py)
- [`runtime/settings.py`](../runtime/settings.py)
- [`pipelines/selfplay_actor.py`](../pipelines/selfplay_actor.py)
- [`pipelines/train_online.py`](../pipelines/train_online.py)

## Debugging Guidance

### Training Is Not Advancing

Check these first:

- Whether `online.progress.json` is still updating
- Whether `online.events.jsonl` still contains new `selfplay_chunk` entries
- Whether an actor reported an error via `type=error`
- Whether the coordinator process is still alive

### GPU Utilization Is Low

Check these first:

- `live_queue_depth`
- `selfplay_chunk` arrival spacing
- `actor_workers`
- `active_games_per_actor`
- `chunk_flush_positions` / `chunk_flush_games`
- `runtime.gpu_coordinator.initial/recurrent_max_batch_items`

### Quick Eval Is Taking Too Long

Check these first:

- `quick_eval.process.log`
- `quick_eval.progress.json`
- Whether baseline MCTS is accidentally using official instead of quick budgets

### Value / Policy Does Not Appear to Learn

Check these first:

- Whether current-player perspective is consistent
- Whether `next_*` recurrent targets are generated correctly
- Whether terminal reward / value use the same semantic convention

## Documentation Update Policy

Update docs whenever any of the following changes:

- Config sections are added or removed
- Online runtime topology changes
- Eval gate rules change
- A new game family is added
- Targon run procedures change

Minimum requirement:

- Update [`README.md`](../README.md)
- Update the relevant topical docs

## Things Not Recommended Right Now

- Introduce implicit global registries on the active path
- Make pipelines depend directly on Targon-specific details
- Push family-specific shortcuts back into `train_online.py` or `SearchEngine`
- Mix quick and official budgets together
