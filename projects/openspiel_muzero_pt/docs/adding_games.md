# Adding Games

## Goal

When adding a new OpenSpiel board-game task, prefer reusing:

- `BoardMuZeroNet`
- `SearchEngine`
- The replay / runtime / online training main path

Add code only where family-specific behavior is genuinely required.

## Minimal Integration Steps

### 1. Register the `GameSpec`

In [`affine_registry.py`](../games/affine_registry.py):

- Add the new `task_id`
- Add the new `GameSpec`
- Verify `board_h / board_w / pad_h / pad_w / action_dim / baseline_*`

### 2. Action Codec

In [`action_codecs.py`](../games/action_codecs.py):

- Implement `encode_dense`
- Implement `decode_dense`
- Implement `to_action_planes`
- Implement symmetry / transpose remaps if needed

### 3. State Encoding

In [`encoders.py`](../games/encoders.py):

- Add the encoder for the new family
- Register it in `build_state_encoder()`

Recommendation:

- Keep family specialization here
- Do not scatter board parsing back into `adapters.py`

### 4. Config File

Add the corresponding base config under [`configs/`](../configs).

Current convention:

- The filename should be `variant_name.yaml`
- `test_configs.py` checks that every registered variant has a config file

### 5. Tests

At minimum, add coverage for:

- Action codec roundtrip / symmetry
- Encoder canonicalization
- Model forward shape
- Search smoke
- Config presence

Existing references:

- [`test_action_codecs.py`](../tests/test_action_codecs.py)
- [`test_game_encoders.py`](../tests/test_game_encoders.py)
- [`test_model.py`](../tests/test_model.py)
- [`test_search_smoke.py`](../tests/test_search_smoke.py)
- [`test_configs.py`](../tests/test_configs.py)

## When You Need to Change the Runtime

Usually you do not.

Only consider runtime changes in cases like:

- Action-plane shapes are no longer compatible with the current `to_action_planes`
- Search requests need a new inference lane
- The replay sample schema needs new fields

If you are only adding a new board-game family, prefer changing only:

- `games/`
- `configs/`
- `tests/`

## Hex-Specific Notes

Hex currently assumes:

- White-to-move uses transpose canonicalization
- Action remapping must stay consistent with that canonicalization

There are already concrete examples of this in [`encoders.py`](../games/encoders.py) and [`action_codecs.py`](../games/action_codecs.py).

## Pre-Commit Checks

At minimum, run:

```bash
./.venv-all/bin/python -m compileall projects/openspiel_muzero_pt
./.venv-muzero/bin/python -m pytest -q projects/openspiel_muzero_pt/tests
```
