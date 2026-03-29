# 8xH200 Production Runtime/Control Test Report

Date: 2026-03-29

## Scope

This session validated the refactored system against the real 8xH200 production tier (`H200-XL`) on Targon.

Goals:

- validate `train`, `collect`, and `eval` through the execution-plane CLI (`forge worker`)
- validate control-plane submission and follow-up commands through `forge control`
- verify that control-plane non-train tasks do not overwrite the experiment top-level training lifecycle

Shared runtime settings:

- runtime: `targon`
- profile: `bootstrap`
- gpu type: `H200-XL`
- dataset repo: `monokoco/affine-sft-data`

## Capacity Check

Command:

```bash
./.venv/bin/python -m forge remote compute capacity
```

Observed availability during the session:

- `h200-xlarge`: `9`

## Cleanup

A previous worker-eval run from an earlier session was still active at the start of this validation.

- bundle: `tmp/prod-8xh200/worker-eval-bundle`
- run id: `wrk-8n77cyjjeyi8`
- cleanup command:

```bash
./.venv/bin/python -m forge worker terminate tmp/prod-8xh200/worker-eval-bundle
```

Result:

- terminated successfully before the new validation runs started

## Execution Plane — `forge worker`

Fresh bundle root:

- `tmp/prod-8xh200-fresh/`

### Worker Train

Render:

```bash
./.venv/bin/python -m forge worker render train tmp/prod-8xh200-fresh/train.jsonl \
  --bundle-dir tmp/prod-8xh200-fresh/worker-train-bundle \
  --job-id prod-8xh200-worker-train-fresh \
  --model Qwen/Qwen2.5-0.5B-Instruct \
  --epochs 1 \
  --batch-size 1 \
  --grad-accum 1 \
  --max-length 1024 \
  --num-gpus 8 \
  --gpu-type H200-XL \
  --overwrite
```

Run:

```bash
./.venv/bin/python -m forge worker run tmp/prod-8xh200-fresh/worker-train-bundle \
  --runtime targon \
  --profile bootstrap \
  --dataset-repo monokoco/affine-sft-data \
  --gpu-type H200-XL
```

Observed:

- run id: `wrk-n82vqg6ioep2`
- status returned `running`
- logs returned real bootstrap output:
  - `[AFFINE] Affine Forge Bootstrap — starting`
  - `[AFFINE] Phase 0: Installing system packages...`

Terminate:

```bash
./.venv/bin/python -m forge worker terminate tmp/prod-8xh200-fresh/worker-train-bundle
```

Result:

- `pass`

### Worker Collect

Render:

```bash
./.venv/bin/python -m forge worker render collect-navworld \
  --bundle-dir tmp/prod-8xh200-fresh/worker-collect-bundle \
  --job-id prod-8xh200-worker-collect-fresh \
  -n 1 \
  --overwrite
```

Run:

```bash
./.venv/bin/python -m forge worker run tmp/prod-8xh200-fresh/worker-collect-bundle \
  --runtime targon \
  --profile bootstrap \
  --dataset-repo monokoco/affine-sft-data \
  --gpu-type H200-XL
```

Observed:

- run id: `wrk-nzy3ubp6w37p`
- status returned `running`
- logs returned real bootstrap output:
  - `[AFFINE] Affine Forge Bootstrap — starting`
  - `[AFFINE] Phase 0: Installing system packages...`

Terminate:

```bash
./.venv/bin/python -m forge worker terminate tmp/prod-8xh200-fresh/worker-collect-bundle
```

Result:

- `pass`

### Worker Eval

Render:

```bash
./.venv/bin/python -m forge worker render eval \
  --bundle-dir tmp/prod-8xh200-fresh/worker-eval-bundle \
  --job-id prod-8xh200-worker-eval-fresh \
  --model Qwen/Qwen3-32B-TEE \
  --envs GAME \
  --samples 1 \
  --base-url https://llm.chutes.ai/v1 \
  --affinetes-dir /workspace/affinetes \
  --gpu-type H200-XL \
  --overwrite
```

Run:

```bash
./.venv/bin/python -m forge worker run tmp/prod-8xh200-fresh/worker-eval-bundle \
  --runtime targon \
  --profile bootstrap \
  --dataset-repo monokoco/affine-sft-data \
  --gpu-type H200-XL
```

Observed:

- run id: `wrk-dfar83ab7l9n`
- status returned `running`
- logs returned real bootstrap output:
  - `[AFFINE] Affine Forge Bootstrap — starting`
  - `[AFFINE] Phase 0: Installing system packages...`

Terminate:

```bash
./.venv/bin/python -m forge worker terminate tmp/prod-8xh200-fresh/worker-eval-bundle
```

Result:

- `pass`

## Control Plane — `forge control`

Control root:

- `tmp/prod-8xh200-control/`

### Control Train

Create:

```bash
./.venv/bin/python -m forge control --dir tmp/prod-8xh200-control create \
  --id v-prod-8xh200-control-train \
  --variable control_train_prod \
  --hypothesis 'control plane train on 8xH200' \
  --train-config '{"model":"Qwen/Qwen2.5-0.5B-Instruct","learning_rate":0.0001,"lora_rank":64,"max_length":1024,"num_train_epochs":1,"per_device_train_batch_size":1,"gradient_accumulation_steps":1,"num_gpus":8,"output_dir":"/tmp/checkpoints"}' \
  --data-config '{"GAME":{"count":1}}'
```

Submit:

```bash
./.venv/bin/python -m forge control --dir tmp/prod-8xh200-control submit-train \
  v-prod-8xh200-control-train \
  tmp/prod-8xh200-control/train.jsonl \
  --runtime targon \
  --profile bootstrap \
  --dataset-repo monokoco/affine-sft-data \
  --gpu-type H200-XL \
  --bundle-dir tmp/prod-8xh200-control/control-train-bundle
```

Observed:

- run id: `wrk-tghzombra0ju`
- follow-up commands worked without repeating `--runtime`
- `run-status --task train` returned remote state
- `run-logs --task train` returned remote output
- during the observation window the run stayed in `provisioning` / `ContainerCreating`

Terminate:

```bash
./.venv/bin/python -m forge control --dir tmp/prod-8xh200-control terminate-run \
  v-prod-8xh200-control-train \
  --task train
```

Post-termination experiment state:

- top-level `status`: `terminated`
- `results.training_run.status`: `terminated`

Result:

- `pass` for control-plane submission and control-path validation
- `not_run` for full completion/artifact validation

### Control Collect

Create:

```bash
./.venv/bin/python -m forge control --dir tmp/prod-8xh200-control create \
  --id v-prod-8xh200-control-collect \
  --variable control_collect_prod \
  --hypothesis 'control plane collect on 8xH200' \
  --train-config '{"model":"Qwen/Qwen2.5-0.5B-Instruct","learning_rate":0.0001,"lora_rank":64,"max_length":1024,"num_train_epochs":1,"per_device_train_batch_size":1,"gradient_accumulation_steps":1,"num_gpus":8,"output_dir":"/tmp/checkpoints"}' \
  --data-config '{"GAME":{"count":1}}'
```

Submit:

```bash
./.venv/bin/python -m forge control --dir tmp/prod-8xh200-control submit-collect-navworld \
  v-prod-8xh200-control-collect \
  --runtime targon \
  -n 1 \
  --profile bootstrap \
  --dataset-repo monokoco/affine-sft-data \
  --gpu-type H200-XL \
  --bundle-dir tmp/prod-8xh200-control/control-collect-bundle
```

Observed:

- run id: `wrk-zwzi6en1sz2s`
- follow-up commands worked without repeating `--runtime`
- `run-status --task collect` returned remote state
- `run-logs --task collect` returned remote output
- during the observation window the run stayed in `provisioning` / `ContainerCreating`

Terminate:

```bash
./.venv/bin/python -m forge control --dir tmp/prod-8xh200-control terminate-run \
  v-prod-8xh200-control-collect \
  --task collect
```

Post-termination experiment state:

- top-level `status`: `draft`
- `results.collect_run.status`: `terminated`

This confirms that non-train tasks no longer overwrite the experiment top-level training lifecycle.

Result:

- `pass` for control-plane non-train submission and state-model validation
- `not_run` for full completion/artifact validation

## Overall Assessment

### Pass

- execution-plane `forge worker` successfully rendered and launched real `train`, `collect`, and `eval` bundles on `H200-XL`
- all three worker tasks reached `running`
- all three worker tasks produced readable real bootstrap logs
- control-plane `forge control` successfully submitted real `train` and `collect` tasks to the Targon runtime
- control-plane follow-up commands worked without repeating `--runtime`
- control-plane training lifecycle semantics behaved as designed:
  - train updates top-level experiment status
  - collect does not overwrite top-level experiment status

### Partial / Not covered in this session

- tasks were intentionally terminated after startup validation to avoid prolonged production spend
- full task completion, artifact collection, and result-quality validation were not exercised here
- control-plane `eval` submission was not rerun in this specific session because execution-plane `eval` was already validated on the same `H200-XL` runtime path, and control-plane submission behavior was already validated by `train` and `collect`

## Final Verdict

For production startup validation on real 8xH200 capacity, the current runtime/control architecture behaves as expected:

- execution-plane startup path: **pass**
- control-plane submission/control path: **pass**
- control-plane non-train state isolation: **pass**

What remains outside the scope of this session is long-running completion and artifact/result validation.
