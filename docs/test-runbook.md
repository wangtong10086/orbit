# Test Runbook

This runbook lists practical validation commands for the current repository
surface. Use it after documentation or runtime-facing changes.

## 1. CLI Surface

```bash
python -m forge --help
python -m forge control --help
python -m forge worker --help
python -m forge data --help
python -m forge remote --help
python -m forge monitor --help
```

Purpose:

- verify root command loading
- verify command-family help remains aligned with docs

## 2. Focused Regression Suite

```bash
pytest -q tests/test_compute.py tests/test_control.py tests/test_data_cli.py tests/test_execution.py -q
```

Expected result:

- passing

## 3. Full Regression Suite

```bash
pytest -q tests -q
```

Expected result:

- passing

## 4. Control-Plane Quick Flow

```bash
python -m forge control experiment create \
  --id v-doc \
  --variable docs \
  --hypothesis "doc sync" \
  --train-config '{}' \
  --data-config '{}'

python -m forge control experiment show v-doc
python -m forge control prepare train v-doc tmp/game_train.jsonl --bundle-dir tmp/bundle-doc-train
```

Note:

- `tmp/game_train.jsonl` must already exist

## 5. Template-Driven Submit Flow

```bash
python -m forge control template list
python -m forge control submit train v-doc tmp/game_train.jsonl --template local-host --bundle-dir tmp/bundle-doc-train --foreground
```

## 5a. Config-Driven Training Launch

```bash
python -m forge control launch train \
  --config examples/official/training/targon-qwen3-32b-full-sft.yaml
```

Expected result:

- the command prints a JSON launch record
- a new experiment file is created
- a training run is submitted through the control plane

## 6. Local Docker Smoke

Run only when local Docker is available:

```bash
python -m forge worker run tmp/bundle-doc-train --placement local --launch-mode docker_image --foreground
python -m forge worker collect tmp/bundle-doc-train
sed -n '1,120p' tmp/bundle-doc-train/runtime/runtime.log
```

## 7. Targon Rental Smoke

Run only when you have an isolated rental machine and a suitable image:

```bash
python -m forge worker run \
  tmp/bundle-doc-train \
  --placement targon_rental \
  --launch-mode docker_image \
  --target <rental-machine> \
  --image wangtong123/affine-forge:latest

python -m forge worker status tmp/bundle-doc-train
python -m forge worker logs tmp/bundle-doc-train --tail 100
python -m forge worker collect tmp/bundle-doc-train
sed -n '1,120p' tmp/bundle-doc-train/runtime/runtime.log
```

## Usage Rule

- after a documentation-only change, run Section 1 at minimum
- after CLI or runtime-path changes, run Sections 1 through 3
- after Targon-facing changes, update and review
  [refactor/real-test-plan.md](refactor/real-test-plan.md)
