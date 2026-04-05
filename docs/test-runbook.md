# Test Runbook

This runbook lists practical validation commands for the current repository
surface. Use it after documentation or runtime-facing changes.

The primary documented deployment pattern for this repository is local
`control` plus Targon execution, so this runbook puts the Targon path first.

## 1. CLI Surface

```bash
python3 -m orbit --help
python3 -m orbit control --help
python3 -m orbit worker --help
python3 -m orbit data --help
python3 -m orbit remote --help
python3 -m orbit monitor --help
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

## 4. Primary Targon Control-Plane Flow

Create an experiment record:

```bash
python3 -m orbit control experiment create \
  --id v-doc \
  --variable "targon runbook" \
  --hypothesis "local control can submit a lightweight NAVWORLD job to Targon" \
  --train-config '{}' \
  --data-config '{}'
```

List templates:

```bash
python3 -m orbit control template list
```

Submit a lightweight remote collection job:

```bash
python3 -m orbit control submit collect \
  v-doc \
  --template targon-rental-host \
  --env NAVWORLD \
  -n 1 \
  -o navworld.jsonl \
  --bundle-dir /tmp/affine-doc-runbook \
  --target <target-machine> \
  --foreground
```

Inspect and collect the run:

```bash
python3 -m orbit control run status v-doc collect
python3 -m orbit control run logs v-doc collect --tail 100
python3 -m orbit control run collect v-doc collect
```

Expected result:

- run submission succeeds through `targon-rental-host`
- `run status` reports the recorded remote run
- `run logs` returns task or runtime logs
- `run collect` pulls artifacts back into the bundle directory

## 5. Config-Driven Training Launch

```bash
python3 -m orbit control launch train \
  --config examples/official/training/targon-qwen3-32b-full-sft.yaml
```

Expected result:

- the command prints a JSON launch record
- a new experiment file is created
- a training run is submitted through the control plane onto Targon

## 6. Config-Driven VG-SOPD Launch

```bash
python3 -m orbit control launch vg-sopd \
  --config examples/vg_sopd_minimal.yaml
```

Expected result:

- the command prints a JSON launch record
- a new experiment file is created
- staged task runs are recorded under experiment `task_runs`

Stage inspection examples:

```bash
python3 -m orbit control run status <exp-id> train --run-key cold_start.sft
python3 -m orbit control run logs <exp-id> train --run-key cold_start.sft --tail 100
```

## 7. Secondary Local Host / Docker Debugging

Use the local worker flows when you want to debug a bundle locally rather than
validate the primary Targon path.

### Local host-process smoke

```bash
python3 -m orbit worker run <bundle-dir> --placement local --launch-mode host_process --foreground
python3 -m orbit worker collect <bundle-dir>
sed -n '1,120p' <bundle-dir>/runtime/runtime.log
```

### Local Docker smoke

Run only when local Docker is available:

```bash
python3 -m orbit worker run <bundle-dir> --placement local --launch-mode docker_image --foreground
python3 -m orbit worker collect <bundle-dir>
sed -n '1,120p' <bundle-dir>/runtime/runtime.log
```

## Usage Rule

- after a documentation-only change, run Section 1 at minimum
- after CLI or runtime-path changes, run Sections 1 through 3
- after Targon-facing changes, update the relevant runtime validation notes in
  the active docs set
