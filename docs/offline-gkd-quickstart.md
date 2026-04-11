# Offline-topk GKD Quickstart

This guide is the practical companion to
[`offline-gkd.md`](offline-gkd.md).

Use this document when you want to actually run the full offline-topk flow:

1. prepare a normal `messages` dataset
2. collect teacher top-k data once
3. launch native `ms-swift` GKD from that offline dataset
4. optionally push the final model or adapter to Hugging Face

This guide is intentionally explicit. It avoids hidden assumptions about which
fields must exist, which secrets are needed at each step, and which values must
match between collection and training.

## What This Path Does

The offline-topk path decouples teacher collection from student training.

- collection talks to the teacher once and writes `teacher_topk_*` fields into
  the dataset
- training consumes only the offline dataset
- training does not load `teacher_model`
- training does not call `teacher_model_server`

If you want the design and architecture view, read
[`offline-gkd.md`](offline-gkd.md).

## Before You Start

You need to decide four things up front:

1. the student model family
2. the teacher source
3. the dataset path
4. whether the training result should be uploaded to Hugging Face

### Required Inputs

Student model:

- this is the model you will train with `orbit control launch train`
- for the official smoke examples in this repository, use
  `Qwen/Qwen3-0.6B`

Teacher source:

- the current recommended path for large teachers is an OpenAI-compatible
  teacher server
- the server must support `prompt_logprobs`
- the server must support `top_logprobs >= gkd_logits_topk`

Dataset:

- offline collection input must be a normal `messages` dataset
- offline training input must be the collected dataset that already contains
  `response_token_ids`, `teacher_topk_indices`, and
  `teacher_topk_logprobs`

Hugging Face publishing:

- optional
- if you want ORBIT to create or update the final model repo, you need
  `HF_TOKEN`

### Required Secrets By Stage

Collection only:

- teacher access only
- for an external teacher server, no ORBIT secret is required if you run
  `swift sample` directly

Training on Targon:

- `HF_TOKEN`
- `TARGON_API_KEY`
- `TARGON_PROJECT_ID`
- `TARGON_SSH_KEY_UID`

Training with upload enabled:

- `HF_TOKEN`
- plus the Targon credentials above if you run on Targon

### Critical Matching Rule

The `swift sample --sampler_type gkd_topk` step must use a tokenizer-compatible
student model.

In practice:

- use the same `--model` in the sampling step as the student `training.model`
- do not collect top-k data with one tokenizer family and train a different
  tokenizer family

For example:

- collect with `--model Qwen/Qwen3-0.6B`
- train with `training.model: Qwen/Qwen3-0.6B`

That is the safest path for `response_token_ids` alignment.

## Stage 1: Prepare The Input Dataset

The collection input is a normal `messages` dataset.

Minimum row shape:

```json
{
  "messages": [
    {"role": "user", "content": "Say OK."},
    {"role": "assistant", "content": "OK"}
  ]
}
```

Rules:

- the last message must be `assistant`
- the last assistant message is the target response that will receive teacher
  top-k annotations
- do not pre-add `teacher_topk_*` fields to the source dataset

Save that source file, for example:

- `/tmp/offline-gkd/input.jsonl`

## Stage 2: Start Or Verify The Teacher Server

If you are using an external teacher server:

- it must expose an OpenAI-compatible API
- it must support `prompt_logprobs`
- it must allow `top_logprobs >= gkd_logits_topk`

For `gkd_logits_topk: 20`, the minimal check is:

```bash
curl -s http://<teacher-host>:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"Qwen/Qwen3-235B-A22B","messages":[{"role":"user","content":"hi"}],"max_tokens":1,"logprobs":true,"top_logprobs":20}'
```

If you want the repository's reusable teacher-side launch template, use:

- [`../scripts/vllm_teacher_qwen3_235b_tp8.sh`](../scripts/vllm_teacher_qwen3_235b_tp8.sh)

## Stage 3: Collect Offline Top-k Data

The repository now supports:

```bash
swift sample --sampler_type gkd_topk
```

The official teacher-server template is:

- [`../examples/official/sampling/gkd-topk-from-teacher-server.sh`](../examples/official/sampling/gkd-topk-from-teacher-server.sh)

The official durable template, which samples and then uploads the sampled file
to a Hugging Face dataset repo, is:

- [`../examples/official/sampling/gkd-topk-from-teacher-server-to-hf.sh`](../examples/official/sampling/gkd-topk-from-teacher-server-to-hf.sh)

The same flow, written inline:

```bash
swift sample \
  --model Qwen/Qwen3-0.6B \
  --sampler_type gkd_topk \
  --teacher_model_server http://<teacher-host>:8000 \
  --gkd_logits_topk 20 \
  --dataset /tmp/offline-gkd/input.jsonl \
  --output_dir /tmp/offline-gkd/output \
  --output_file offline_topk.jsonl
```

Important meanings:

- `--model`
  - this is the student-side tokenizer/model family used to build
    `response_token_ids`
- `--teacher_model_server`
  - this is the teacher inference endpoint
- `--gkd_logits_topk`
  - this defines the width of `teacher_topk_indices` and
    `teacher_topk_logprobs`
- `--dataset`
  - this is the input `messages` dataset
- `--output_dir`
  - this is the directory where the collected dataset will be written
- `--output_file`
  - this is the collected JSONL file name inside `output_dir`

After collection, the output file is:

- `/tmp/offline-gkd/output/offline_topk.jsonl`

Recommended production rule:

- do not leave the only copy of sampled offline-topk data on a local disk or a
  rental filesystem
- upload the sampled JSONL to a Hugging Face dataset repo immediately after
  validation

The repository now includes a wrapper that does exactly that:

```bash
bash examples/official/sampling/gkd-topk-from-teacher-server-to-hf.sh
```

That wrapper:

1. runs `swift sample --sampler_type gkd_topk`
2. validates the output JSONL
3. uploads it to a Hugging Face dataset repo under `offline_topk/...`

Like `orbit control launch train`, the wrapper also backfills missing
environment variables from the repository `.env` and then the parent `.env`.
So `HF_TOKEN` and `HF_DATASET_REPO` can come either from:

- the current shell
- the repository `.env`
- the parent-directory `.env`

### Production Collection Path

For canonical-scale collection, do not use many parallel `swift sample`
processes as the primary path.

The repository now includes a production collector that:

1. scans the source dataset once
2. filters out rows longer than `32k`
3. pre-encodes teacher-request inputs once
4. splits rows into `b8 / b16 / b32`
5. collects offline top-k data with bounded teacher concurrency
6. flushes part files incrementally
7. uploads each part to a Hugging Face dataset repo

Use:

```bash
bash examples/official/sampling/collect-offline-topk-canonical.sh
```

Or run the Python entrypoint directly:

```bash
python3 scripts/collect_offline_topk_dataset.py \
  --dataset /tmp/offline-gkd/input.jsonl \
  --output-dir /tmp/offline-gkd/collect \
  --model Qwen/Qwen3-0.6B \
  --teacher-model-server http://<teacher-host>:8000 \
  --gkd-logits-topk 20 \
  --max-length 32768 \
  --bucket-boundaries 8192,16384,32768 \
  --hf-repo user/offline-topk-dataset \
  --hf-prefix offline_topk/demo \
  --create-repo
```

This command writes:

- `prepared_manifest.json`
- `collection_manifest.json`
- `collected/b8/part-*.jsonl`
- `collected/b16/part-*.jsonl`
- `collected/b32/part-*.jsonl`

The final part files are already in the same response-only offline-topk schema
that `offline_topk` GKD training consumes.

## Stage 4: Validate The Collected Dataset

The collected dataset must now contain:

- `messages`
- `response_token_ids`
- `teacher_topk_indices`
- `teacher_topk_logprobs`

Quick structural check:

```bash
python3 - <<'PY'
import json
from pathlib import Path

row = json.loads(Path('/tmp/offline-gkd/output/offline_topk.jsonl').read_text().splitlines()[0])
for key in [
    'messages',
    'response_token_ids',
    'teacher_topk_indices',
    'teacher_topk_logprobs',
]:
    if key not in row:
        raise SystemExit(f'missing required field: {key}')

print('fields ok')
print('assistant message:', row['messages'][-1]['content'])
print('response token count:', len(row['response_token_ids']))
print('teacher rows:', len(row['teacher_topk_indices']))
print('teacher topk width:', len(row['teacher_topk_indices'][0]) if row['teacher_topk_indices'] else 0)
PY
```

What to expect:

- `response token count` and `teacher rows` should usually match
- `teacher topk width` should equal `gkd_logits_topk`

## Stage 5: Choose A Training Config

There are now two official offline-topk training examples.

Smoke-style training without publishing:

- [`../examples/official/training/targon-qwen3-0.6b-gkd-offline-topk.yaml`](../examples/official/training/targon-qwen3-0.6b-gkd-offline-topk.yaml)

End-to-end training with Hugging Face upload enabled:

- [`../examples/official/training/targon-qwen3-0.6b-gkd-offline-topk-push-to-hf.yaml`](../examples/official/training/targon-qwen3-0.6b-gkd-offline-topk-push-to-hf.yaml)

Edit at minimum:

- `experiment.id`
- `dataset.path`
- `publish.hub_model_id` if upload is enabled
- `execution.target.workload_name`
- `execution.target.machine_name`

### What Must Be True In The Training Config

For offline-topk training:

- `training.train_type: rlhf`
- `training.rlhf_type: gkd`
- `training.teacher_data_mode: offline_topk`

And these must stay unset:

- `training.teacher_model`
- `training.swift_passthrough.teacher_model_server`

This is the main semantic difference from online-teacher GKD.

## Stage 6: Launch Training

Example launch:

```bash
python3 -m orbit control launch train \
  --config examples/official/training/targon-qwen3-0.6b-gkd-offline-topk.yaml
```

If you want the run to create or update a Hugging Face model repo:

```bash
python3 -m orbit control launch train \
  --config examples/official/training/targon-qwen3-0.6b-gkd-offline-topk-push-to-hf.yaml
```

Expected runtime behavior:

- ORBIT stages the bundle
- the rental entrypoint applies `apply_ms_swift_patches.py`
- native `swift rlhf` runs with `teacher_data_mode=offline_topk`
- training reads `teacher_topk_*` from the dataset
- training does not load a teacher
- training does not call a teacher server

## Stage 7: Monitor The Run

Control-plane status:

```bash
python3 -m orbit control run status <experiment-id> train
```

Tail runtime logs:

```bash
python3 -m orbit control run logs <experiment-id> train --tail 200
```

Key log lines to confirm:

- `applying ms-swift runtime patches`
- `native GKD runtime check passed`
- `--teacher_data_mode offline_topk`
- `teacher_model=None`
- `teacher_model_server=None`

If the run succeeds, collect artifacts:

```bash
python3 -m orbit control run collect <experiment-id> train
```

## Stage 8: Verify Hugging Face Upload

This step only applies when:

- `publish.push_to_hub: true`

Expected result:

- ORBIT writes the final model or adapter artifact to `publish.hub_model_id`
- the target Hugging Face repo contains model files and a generated `README.md`

Typical verification:

```bash
python3 -m orbit control run status <experiment-id> train
python3 -m orbit control run collect <experiment-id> train
```

Then verify the target Hugging Face repo contents with your normal Hugging Face
tools.

## Recommended Persistence Pattern

Use two Hugging Face repos, not one:

- dataset repo for sampled offline-topk data
- model repo for trained student artifacts

Recommended split:

- sampled teacher data:
  - repo type `dataset`
  - path like `offline_topk/<run-or-bucket>.jsonl`
- trained student output:
  - repo type `model`

This keeps:

- collection artifacts durable and versioned
- training output separate from teacher data
- reruns reproducible without recollecting teacher top-k data

## Complete E2E Example

This is the shortest complete path:

1. prepare `/tmp/offline-gkd/input.jsonl`
2. verify the teacher server supports `top_logprobs=20`
3. run `swift sample --sampler_type gkd_topk`
4. inspect `/tmp/offline-gkd/output/offline_topk.jsonl`
5. edit
   [`../examples/official/training/targon-qwen3-0.6b-gkd-offline-topk-push-to-hf.yaml`](../examples/official/training/targon-qwen3-0.6b-gkd-offline-topk-push-to-hf.yaml)
6. run `python3 -m orbit control launch train --config ...`
7. wait for `run status` to become `succeeded`
8. verify the target Hugging Face repo contains the uploaded artifact

## Common Failure Modes

### `teacher_topk_*` fields disappear during training

Cause:

- the runtime did not apply the ORBIT `ms-swift` patch set

What to check:

- remote logs contain `applying ms-swift runtime patches`

### `response_token_ids` do not align with training labels

Cause:

- collection used a tokenizer family that does not match the student model
- or the assistant response text changed between collection and training

What to do:

- keep the same student model family for collection and training
- do not mutate the assistant response after collection

### Training still tries to contact a teacher

Cause:

- the config is not actually using `teacher_data_mode: offline_topk`
- or `teacher_model_server` was still passed through under
  `swift_passthrough`

What to do:

- confirm the effective config in experiment YAML
- confirm the runtime command includes `--teacher_data_mode offline_topk`
- confirm `teacher_model=None` and `teacher_model_server=None` in the logs

### Hugging Face upload does not happen

Cause:

- `publish.push_to_hub` is still `false`
- `HF_TOKEN` is missing
- `publish.hub_model_id` was not set correctly

What to do:

- use the publish-enabled example
- verify `HF_TOKEN`
- verify the target repo name

## Related Files

- [`offline-gkd.md`](offline-gkd.md)
- [`official-examples.md`](official-examples.md)
- [`operations.md`](operations.md)
- [`test-runbook.md`](test-runbook.md)
- [`../examples/official/sampling/gkd-topk-from-teacher-server.sh`](../examples/official/sampling/gkd-topk-from-teacher-server.sh)
- [`../examples/official/sampling/gkd-topk-from-teacher-server-to-hf.sh`](../examples/official/sampling/gkd-topk-from-teacher-server-to-hf.sh)
- [`../scripts/sample_offline_topk_and_upload.py`](../scripts/sample_offline_topk_and_upload.py)
- [`../examples/official/training/targon-qwen3-0.6b-gkd-offline-topk.yaml`](../examples/official/training/targon-qwen3-0.6b-gkd-offline-topk.yaml)
- [`../examples/official/training/targon-qwen3-0.6b-gkd-offline-topk-push-to-hf.yaml`](../examples/official/training/targon-qwen3-0.6b-gkd-offline-topk-push-to-hf.yaml)
