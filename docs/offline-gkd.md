# Offline GKD Design

This document explains the patched ORBIT + `ms-swift` offline-topk GKD path.
It is the current design note for the repository's "offline distillation"
workflow.

If you want the step-by-step operator guide, use
[`offline-gkd-quickstart.md`](offline-gkd-quickstart.md).
This file stays focused on architecture, contracts, and runtime behavior.

The goal is to decouple two expensive phases:

- teacher-side top-k collection
- student-side GKD training

In this design, ORBIT does not orchestrate a separate distillation pipeline.
Instead it:

- helps generate offline teacher top-k data
- passes that dataset into the normal `training_launch` path
- runs native `ms-swift` GKD with `teacher_data_mode: offline_topk`

Training then runs without:

- `teacher_model`
- `teacher_model_server`
- online teacher API calls during each training step

## Design Summary

The offline-topk path has three major stages:

1. prepare a normal `messages` dataset
2. run offline teacher sampling once to attach top-k teacher data
3. train the student from that augmented dataset through
   `orbit control launch train`

The critical contract is:

- sampling owns teacher access
- training consumes teacher data only from the dataset

## Control / Data / Runtime Split

```text
+-------------------------------+
| Teacher Service / Teacher     |
| Model                         |
+-------------------------------+
                |
                | offline top-k sampling
                v
+-------------------------------+
| Offline top-k dataset         |
| messages + response_token_ids |
| + teacher_topk_*              |
+-------------------------------+
                |
                | training_launch dataset input
                v
+-------------------------------+
| ORBIT control plane           |
+-------------------------------+
                |
                | generic training bundle
                v
+-------------------------------+
| Execution plane               |
+-------------------------------+
                |
                | swift rlhf
                | --teacher_data_mode offline_topk
                v
+-------------------------------+
| Student training on rental    |
| or local host                 |
+-------------------------------+
```

The important boundary is that teacher access ends before the training bundle
starts.

## Architecture View

```text
+---------------------------------------------------------------+
| ORBIT control plane                                           |
|                                                               |
|  +-------------------+    +-------------------------------+   |
|  | training_launch   | -> | Training launcher             |   |
|  +-------------------+    +-------------------------------+   |
|                                  |                            |
|                                  v                            |
|                         +-------------------------------+     |
|                         | TrainingSpec / experiment     |     |
|                         | record                        |     |
|                         +-------------------------------+     |
+---------------------------------------------------------------+

+---------------------------------------------------------------+
| Execution bundle                                              |
|                                                               |
|  +-------------------+   +-------------------------------+    |
|  | swift_config.yaml |   | apply_ms_swift_patches.py     |    |
|  +-------------------+   +-------------------------------+    |
|                 \\             /                               |
|                  \\           /                                |
|                   v         v                                 |
|                 +-------------------------------+             |
|                 | entrypoint.sh                 |             |
|                 +-------------------------------+             |
+---------------------------------------------------------------+

+---------------------------------------------------------------+
| patched ms-swift                                              |
|                                                               |
|  +--------------------------------------+                     |
|  | swift sample --sampler_type gkd_topk |                     |
|  +--------------------------------------+                     |
|  +--------------------------------------+                     |
|  | GKD trainer offline_topk mode        |                     |
|  +--------------------------------------+                     |
+---------------------------------------------------------------+

+---------------------------------------------------------------+
| Dataset                                                       |
|                                                               |
|  +---------------------+                                      |
|  | messages-only source|                                      |
|  +---------------------+                                      |
|             |                                                 |
|             v                                                 |
|  +---------------------------------------------+              |
|  | messages + response_token_ids +             |              |
|  | teacher_topk_*                              |              |
|  +---------------------------------------------+              |
+---------------------------------------------------------------+

Flow:
  messages-only source
    -> swift sample --sampler_type gkd_topk
    -> offline top-k dataset
    -> training_launch / TrainingSpec
    -> bundle files + entrypoint patch step
    -> GKD trainer offline_topk mode
```

## End-to-End Sequence

```text
User
  |
  | 1. swift sample --sampler_type gkd_topk
  v
Teacher sampler
  |
  | 2. write response_token_ids + teacher_topk_*
  v
Offline dataset
  |
  | 3. orbit control launch train --config ...
  v
ORBIT control
  |
  | 4. submit training bundle
  v
Targon rental / local worker
  |
  | 5. apply_ms_swift_patches.py
  | 6. swift rlhf --teacher_data_mode offline_topk
  v
patched ms-swift trainer
  |
  | 7. read offline top-k fields from dataset
  | 8. align top-k rows to assistant loss positions
  | 9. compute GKD loss without online teacher calls
  v
logs / checkpoints / final state
  |
  | 10. report status back
  v
ORBIT control
```

## Dataset Schema

v1 uses a response-only top-k schema.

Each row contains:

- `messages`
  - standard `ms-swift` conversation sample
  - the last assistant message is the student target response
- `response_token_ids`
  - token ids corresponding to the teacher-sampled assistant response span
- `teacher_topk_indices`
  - shape `[response_len][topk]`
- `teacher_topk_logprobs`
  - shape `[response_len][topk]`

Optional metadata may also appear:

- `teacher_model_name`
- `teacher_topk`
- `teacher_source`
- `teacher_generated_at`
- `teacher_prompt_template_hash`
- `teacher_topk_storage_dtype`

Example shape:

```json
{
  "messages": [
    {"role": "user", "content": "Say OK."},
    {"role": "assistant", "content": "OK"}
  ],
  "response_token_ids": [151667, 271, 151668, 271, 3925, 151645, 198],
  "teacher_topk_indices": [[151667, 151668], [198, 271]],
  "teacher_topk_logprobs": [[0.0, -20.625], [-0.00018, -8.625]],
  "teacher_topk": 20,
  "teacher_source": "teacher_model_server"
}
```

## Training Config Contract

The offline-topk training path is enabled by:

```yaml
training:
  train_type: rlhf
  rlhf_type: gkd
  teacher_data_mode: offline_topk
  swift_passthrough:
    gkd_logits_topk: 20
```

Important rules:

- do not set `teacher_model`
- do not set `teacher_model_server`
- the dataset itself becomes the teacher source

ORBIT persists this explicitly:

- top-level `experiment.train_config` stores the effective config
- `results.extra.training_launch_config_declared` stores the raw launch file
- `results.extra.training_launch_config_resolved` stores the resolved launch
  config

For offline-topk runs, the effective config also records:

- `teacher_data_mode`
- `teacher_topk_indices_field`
- `teacher_topk_logprobs_field`
- `teacher_response_token_ids_field`
- `teacher_topk_storage_dtype`

## Runtime Behavior

The bundle entrypoint performs these steps for native GKD:

1. activate the runtime environment
2. apply ORBIT's tracked `ms-swift` patch set
3. run the native GKD runtime precheck
4. execute `swift rlhf --config ...`

For `teacher_data_mode: offline_topk`, the runtime precheck changes:

- required: `torch`, `transformers`, `swift`
- not required: `vllm`

That is different from `teacher_model_server` mode, which still requires
`vllm`.

## Offline Sampling Path

The patched repository adds:

```bash
swift sample --sampler_type gkd_topk
```

Supported teacher sources:

- `--teacher_model_server ...`
- `--teacher_model ...`

The current implementation writes JSONL rows with the response-only top-k
schema above.

Current real-validated shape:

- teacher service: external vLLM OpenAI-compatible server
- top-k: `20`
- sampling command succeeded and wrote a valid JSONL row

## Alignment Logic

The tricky part is aligning offline teacher rows to the student loss positions.

Current trainer behavior:

- `ms-swift` still encodes the full conversation through the normal template
- the trainer reads `labels != -100` to find assistant-loss positions
- offline top-k rows are then aligned onto those positions

Current ORBIT helper behavior:

1. try exact assistant token match
2. if exact match fails, try matching the assistant span as a contiguous
   subsequence of `response_token_ids`
3. if that still fails, fall back to tail alignment using the last
   `min(response_len, label_len)` rows

This fallback exists because offline sampling and training-time template
encoding can insert different assistant-side wrapper tokens around the same
semantic answer.

## Why This Path Exists

The online external-teacher GKD path was real-tested and showed a structural
throughput problem:

- each training step triggered many teacher API requests
- GPU utilization stayed low for large portions of the run
- teacher roundtrips dominated step time

Offline-topk moves that cost out of the training loop:

- teacher collection happens once
- student training runs without online teacher dependency

This improves:

- throughput stability
- auditability
- reproducibility
- decoupling of teacher availability from training availability

## Current Limitations

v1 deliberately keeps the scope narrow:

- response-only top-k, not full prompt logprob caching
- JSONL storage, not parquet
- patched upstream install, not a permanent upstream merge yet
- current field alignment is robust enough for validated smokes, but still
  depends on the active template/tokenization behavior

## Current Real Validation

The following parts have already been real-validated:

- offline teacher sampling via
  `swift sample --sampler_type gkd_topk`
- ORBIT control-plane launch with `teacher_data_mode: offline_topk`
- native GKD bundle generation without `teacher_model` / `teacher_model_server`
- remote runtime patch application on a fresh Targon rental
- rerun of the original failing offline-topk GKD command until it completed
  `1/1` step and wrote `checkpoint-1`

The most recent validated rental workspace for the original failing command was:

- `/root/orbit-execution/real-offline-topk-gkd-smoke-20260409dd`

## Related Files

- [`../scripts/apply_ms_swift_patches.py`](../scripts/apply_ms_swift_patches.py)
- [`../orbit/integrations/ms_swift_offline_topk.py`](../orbit/integrations/ms_swift_offline_topk.py)
- [`../examples/official/training/targon-qwen3-0.6b-gkd-offline-topk.yaml`](../examples/official/training/targon-qwen3-0.6b-gkd-offline-topk.yaml)
- [`official-examples.md`](official-examples.md)
- [`operations.md`](operations.md)
- [`test-runbook.md`](test-runbook.md)
