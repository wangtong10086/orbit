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
- the experiment YAML stores the effective runtime-facing config under
  top-level `train_config`
- the original launch file shape is preserved under
  `results.extra.training_launch_config_declared`

Optional bucketed SFT launch:

```bash
python3 -m orbit control launch train \
  --config examples/official/training/targon-qwen3-32b-full-sft-bucketed.yaml
```

Expected result:

- the bundle writes `artifacts/bucket_manifest.json`
- the remote run emits staged logs named after the configured stage names, for
  example `artifacts/training-sft-8k.log` or `artifacts/training-short.log`
- the final stage is re-exposed at `artifacts/checkpoints`
- the experiment YAML records per-stage effective configs under
  `results.extra.training_bucket_plan_resolved`

## 6. Native RLHF / GKD Training Launch

```bash
python3 -m orbit control launch train \
  --config examples/official/training/targon-qwen3-0.6b-gkd.yaml
```

```bash
python3 -m orbit control launch train \
  --config examples/official/training/targon-qwen3-0.6b-gkd-offline-topk.yaml
```

```bash
python3 scripts/build_ms_swift_canonical_dataset.py \
  /abs/path/canonical/game.jsonl \
  /abs/path/canonical/liveweb.jsonl \
  /abs/path/canonical/memorygym.jsonl \
  /abs/path/canonical/navworld.jsonl \
  /abs/path/canonical/swe_infinite.jsonl \
  -o /tmp/canonical_ms_swift.jsonl \
  --manifest /tmp/canonical_ms_swift_manifest.json

python3 -m orbit control launch train \
  --config examples/official/training/targon-qwen3-32b-full-gkd.yaml
```

Expected result:

- the command prints a JSON launch record
- a new experiment file is created
- a training run is submitted through the normal training plugin
- the remote run executes upstream native `ms-swift` GKD without a separate
  ORBIT distillation stage
- the default image already contains the GKD runtime, including `vllm`
- for `teacher_data_mode: offline_topk`, the run no longer requires
  `teacher_model`, `teacher_model_server`, or `vllm`

Inspection examples:

```bash
python3 -m orbit control run status <exp-id> train
python3 -m orbit control run logs <exp-id> train --tail 100
python3 -m orbit control run collect <exp-id> train
```

Training config rules:

- use `kind: training_launch`
- set `training.train_type: rlhf`
- set `training.rlhf_type: gkd`
- point `dataset` at a prepared native `ms-swift` GKD dataset
- for offline-topk GKD, the dataset must include
  `response_token_ids`, `teacher_topk_indices`, and `teacher_topk_logprobs`
- use `training.swift_passthrough` for upstream flags ORBIT does not model
  directly
- use `teacher_data_mode: offline_topk` when teacher top-k data has already
  been collected offline
- keep the validated default recipe at `attn_impl: sdpa` and `packing: false`
- for 32B GKD on 4xH200, prefer a normalized `messages`-only dataset,
  `tuner_type: full`, and `deepspeed: zero3`
- for the current validated 32B full-GKD debug recipe, use `max_length: 768`
- for bucketed SFT, use the optional top-level `bucketing` block to define
  ordered stages and stage-specific training overrides
- for bucketed full SFT, each stage resumes from the previous stage checkpoint
- for bucketed LoRA SFT, each stage keeps the original base model and adds the
  previous stage checkpoint under `adapters`

## 7. Default Image / Bootstrap Runtime Check

Validate the default image directly:

```bash
docker run --rm wangtong123/orbit:latest \
  python3 -c "import torch, transformers, swift, vllm; print(torch.__version__, transformers.__version__, swift.__version__, vllm.__version__)"
docker run --rm wangtong123/orbit:latest python3 -m swift.cli.rlhf --help >/dev/null
```

Validate bootstrap on a fresh host:

```bash
bash orbit/setup/bootstrap.sh --check
```

Expected result:

- both commands succeed
- `bootstrap.sh --check` reports `vllm`

Offline-topk smoke for patched `ms-swift`:

```bash
swift sample \
  --model Qwen/Qwen3-0.6B \
  --sampler_type gkd_topk \
  --teacher_model_server http://<teacher-host>:8000 \
  --gkd_logits_topk 20 \
  --dataset /abs/path/input.jsonl \
  --output_dir /tmp/gkd-topk-sample
```

Expected result:

- the output JSONL includes:
  - `response_token_ids`
  - `teacher_topk_indices`
  - `teacher_topk_logprobs`
- see [`offline-gkd.md`](offline-gkd.md) for the full offline-topk flow and
  architecture diagrams
- see [`offline-gkd-quickstart.md`](offline-gkd-quickstart.md) for the exact
  e2e collection -> training -> Hugging Face upload path

Durable offline-topk collection smoke:

```bash
bash examples/official/sampling/gkd-topk-from-teacher-server-to-hf.sh
```

Expected result:

- sampling succeeds
- the sampled JSONL validates successfully
- the file is uploaded to a Hugging Face dataset repo under `offline_topk/...`
- if `HF_TOKEN` or `HF_DATASET_REPO` are not exported in the current shell,
  the helper may still succeed by loading them from the repository `.env`

## 8. External Teacher Server Logprob Check

For `gkd_logits_topk: 64`, confirm the teacher server is started with
`--max-logprobs 64` or higher before launching training.

Launch template:

```bash
bash scripts/vllm_teacher_qwen3_235b_tp8.sh
```

The helper script above is included in the public release snapshot.

Probe the server:

```bash
curl -s http://<teacher-host>:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"Qwen/Qwen3-235B-A22B","messages":[{"role":"user","content":"hi"}],"max_tokens":1,"logprobs":true,"top_logprobs":20}' >/dev/null

curl -s http://<teacher-host>:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"Qwen/Qwen3-235B-A22B","messages":[{"role":"user","content":"hi"}],"max_tokens":1,"logprobs":true,"top_logprobs":64}' >/dev/null
```

Expected result:

- both requests succeed
- if the `64` request returns HTTP 400, the server was started with an
  insufficient `--max-logprobs`

## 9. Secondary Local Host / Docker Debugging

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

## Public Snapshot Automation

Dry-run the private-repo public snapshot workflow without publishing:

```bash
gh workflow run publish-public.yml --ref main -f dry_run=true
```

Republish a historical source commit to the public repo:

```bash
gh workflow run publish-public.yml --ref main -f source_sha=<private-source-sha>
```

The automated publish workflow validates the exported snapshot before push and
then waits for public `CI`, `Docs`, and `Docker` on `AffineFoundation/ORBIT`.
