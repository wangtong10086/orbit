# Architecture

## Goal

`openspiel_muzero_pt` is a PyTorch Gumbel MuZero training stack for Affine OpenSpiel board-game tasks.

Current architectural goals:

- Game logic runs directly on `pyspiel`
- Network forward/backward passes are centralized in a single GPU coordinator process
- CPU actors handle environment stepping and Python tree search
- Quick eval and official eval remain explicitly separated
- New games should reuse the runtime / search / replay main path instead of copying Othello-specific code

## Package Structure

### `games/`

Owns game contracts and the OpenSpiel adaptation layer.

- [`game_spec.py`](../games/game_spec.py)
  Static definitions for each game variant.
- [`affine_registry.py`](../games/affine_registry.py)
  The currently registered Othello / Hex / Clobber tasks.
- [`action_codecs.py`](../games/action_codecs.py)
  Mapping between OpenSpiel actions and dense action ids.
- [`encoders.py`](../games/encoders.py)
  Board encoding logic for each family.
- [`adapters.py`](../games/adapters.py)
  OpenSpiel interaction entrypoint. Owns `build_game / new_initial_state / encode_state / legal_action_mask / create_affine_mcts_bot`.

Design constraints:

- Keep `adapter` lightweight; it should only coordinate OpenSpiel interaction and generic wrapping.
- Put family-specific encoding in `encoders.py` so `adapters.py` does not turn into a God module.

### `model/`

- [`board_muzero.py`](../model/board_muzero.py)
  `BoardMuZeroNet`, including `initial_inference` and `recurrent_inference`.

The network only cares about:

- Input tensor shapes
- Latent dynamics
- Policy / value / reward heads

It does not know about concrete OpenSpiel states and does not directly depend on search logic.

### `search/`

- [`tree.py`](../search/tree.py)
  Search node and edge data structures.
- [`puct.py`](../search/puct.py)
  Child selection and backup rules.
- [`gumbel_root.py`](../search/gumbel_root.py)
  Root shortlist / sequential halving.
- [`batched_search.py`](../search/batched_search.py)
  Main batched root-search entrypoint.

Design constraints:

- `SearchEngine` depends on `ModelInferenceClient`, not on a concrete model instance.
- This allows local tests to use the local client while online training uses the brokered client.

### `replay/`

- [`expert_buffer.py`](../replay/expert_buffer.py)
  Expert shard loading and sample packing.
- [`ring_buffer.py`](../replay/ring_buffer.py)
  Preallocated ring buffer for live replay.

Current strategy:

- Expert data comes from `label_with_mcts.py`
- Live data comes from `selfplay_actor.py`
- The learner mixes expert + live samples

### `runtime/`

- [`inference.py`](../runtime/inference.py)
  Local / brokered inference client abstractions.
- [`gpu_coordinator.py`](../runtime/gpu_coordinator.py)
  Single-GPU coordinator that centralizes search inference and train batches.
- [`settings.py`](../runtime/settings.py)
  Online runtime configuration parsing.

This is the main boundary difference between online training and warm-start.

Warm-start:

- Single-process model training
- Does not use the broker runtime

Online:

- CPU actors
- centralized GPU coordinator
- quick eval in a separate process

### `pipelines/`

- [`build_state_corpus.py`](../pipelines/build_state_corpus.py)
- [`label_with_mcts.py`](../pipelines/label_with_mcts.py)
- [`warmstart.py`](../pipelines/warmstart.py)
- [`selfplay_actor.py`](../pipelines/selfplay_actor.py)
- [`train_online.py`](../pipelines/train_online.py)
- [`evaluate_vs_affine_mcts.py`](../pipelines/evaluate_vs_affine_mcts.py)

Together these files define the real execution path from offline teacher data to the online self-play loop.

## Online Training Data Flow

```text
CPU actor(s)
  -> pyspiel state
  -> SearchEngine
  -> BrokeredInferenceClient
GPU coordinator
  -> initial / recurrent inference
  -> train_batch
train_online
  -> ArrayRingBuffer
  -> mixed expert/live sampling
  -> BrokeredTrainClient
  -> checkpoint / quick eval
```

## Config Ownership

Config is split by ownership:

- `game`
  Selects task id and family.
- `model`
  Network width, depth, and head sizes.
- `search`
  Self-play / reanalyse / eval search budgets.
- `optimizer`
  Learning rate, weight decay, and grad clipping.
- `train`
  Learner cadence plus checkpoint / eval cadence.
- `actors`
  CPU self-play parallelism.
- `runtime.gpu_coordinator`
  GPU batching and snapshot sync.
- `buffers`
  Replay capacity.
- `corpus`
  Cheap state-corpus generation.
- `expert`
  Teacher budget for expert labeling.
- `eval`
  Quick / official evaluation gating.

## Current Known Boundaries

- Tree search is still implemented in Python, not as a CUDA tree.
- OpenSpiel environment stepping is still CPU-side.
- Quick eval still uses the current Affine baseline MCTS.
- Othello is still the most mature real-runtime path; Hex / Clobber are structurally integrated but have not yet received the same level of real-machine long-run validation.
