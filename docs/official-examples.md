# Official Remote Examples

This document covers the official remote examples for ORBIT. It is
deliberately centered on Targon because the primary documented use case for this
project is local control plus remote execution on Targon rentals.

## Official Targon Training Example

Use this config as the official production-style training example:

- [`../examples/official/training/targon-qwen3-32b-full-sft.yaml`](../examples/official/training/targon-qwen3-32b-full-sft.yaml)
- [`../examples/official/training/targon-qwen3-32b-full-sft-bucketed.yaml`](../examples/official/training/targon-qwen3-32b-full-sft-bucketed.yaml)

Launch command:

```bash
python3 -m orbit control launch train \
  --config examples/official/training/targon-qwen3-32b-full-sft.yaml
```

Optional bucketed variant:

```bash
python3 -m orbit control launch train \
  --config examples/official/training/targon-qwen3-32b-full-sft-bucketed.yaml
```

The launch flow performed by that config is:

1. validate required environment variables
2. download the dataset file from Hugging Face
3. create the target model repo if needed
4. provision and register a fresh isolated Targon rental
5. create the experiment record
6. submit the training run through the control plane
7. upload the final training artifacts to the configured Hugging Face model repo
   when `publish.push_to_hub=true`

Current dataset handling note:

- the launcher currently downloads or locates the dataset first
- for large local datasets on Targon launches, it stages the dataset into
  `HF_RUNTIME_REPO`/`HF_BACKUP_REPO` and the rental downloads it directly
- smaller datasets may still travel inside the execution bundle

Current bucketed-training note:

- `training_launch` now supports optional length bucketing for native
  `ms-swift` training runs
- when `bucketing` is present, ORBIT still creates one training run, but the
  bundle splits the dataset by token length and runs staged `swift` configs in
  sequence inside the same remote workspace
- `bucketing.mode: auto` derives ranges from ordered stage `max_length` values
  such as `<=8k`, `8k-16k`, and `>16k`
- `bucketing.mode: manual` lets you set explicit `bucket_min_length` and
  `bucket_max_length` per stage
- each stage can override training fields such as
  `per_device_train_batch_size`, `gradient_accumulation_steps`, and
  `dataset_num_proc`
- for `tuner_type: full`, each stage resumes directly from the previous stage
  checkpoint as the new `model`
- for `tuner_type: lora`, each stage keeps the original base model and adds the
  previous stage checkpoint as an adapter, so LoRA bucket continuation does not
  try to load an adapter checkpoint as a standalone base model
- the final stage is aliased back to `artifacts/checkpoints` so downstream
  artifact collection and upload still see the usual checkpoint path
- experiment YAML stores the base effective config at top-level `train_config`
  and the per-stage effective configs under
  `results.extra.training_bucket_plan_resolved`

## Official Targon Evaluation / Collection Entry Points

The same control-to-execution pattern also applies to evaluation and
collection.

Current documentation intentionally focuses on:

- the official training launch above
- the lightweight `submit collect` Targon path used in
  [getting-started.md](getting-started.md)

There is not yet a separate official one-command evaluation config documented at
the same level as the training launch. Evaluation follows the same
`control -> execution template -> Targon target -> run status/logs/collect`
pattern.

## Native GKD Training Example

The repository ships a native `ms-swift` GKD example through the normal
training launcher:

- [`../examples/official/training/targon-qwen3-0.6b-gkd.yaml`](../examples/official/training/targon-qwen3-0.6b-gkd.yaml)
- [`../examples/official/training/targon-qwen3-32b-full-gkd.yaml`](../examples/official/training/targon-qwen3-32b-full-gkd.yaml)

Launch command:

```bash
python3 -m orbit control launch train \
  --config examples/official/training/targon-qwen3-0.6b-gkd.yaml
```

```bash
python3 -m orbit control launch train \
  --config examples/official/training/targon-qwen3-32b-full-gkd.yaml
```

Current policy:

- ORBIT no longer orchestrates a separate distillation workflow
- native `ms-swift` capabilities such as `sft`, `gkd`, and other `rlhf_type`
  values go through `training_launch`
- datasets for native GKD must already be prepared in the format expected by
  `ms-swift`

Current training behavior for native GKD:

- the launch surface is still `orbit control launch train`
- `training.train_type: rlhf` plus `training.rlhf_type: gkd` maps directly to
  upstream `swift rlhf`
- the default execution image and `orbit/setup/bootstrap.sh` now preinstall the
  native GKD runtime, including `vllm`, so first-run remote jobs do not require
  a manual hotfix
- `teacher_model` remains an explicit training-side field
- additional upstream flags can be passed through under
  `training.swift_passthrough`, for example `gkd_logits_topk: 64`
- if the run uses an external `teacher_model_server`, experiment YAML will show
  that effective server-side configuration instead of an empty `teacher_model`
  placeholder
- the currently validated stable recipe is `attn_impl: sdpa` plus
  `packing: false`
- for `Qwen/Qwen3-32B` on 4xH200, the current debugged direction is full
  finetuning with `tuner_type: full` plus `deepspeed: zero3`
- the currently validated 32B full-GKD debug recipe uses `max_length: 768`;
  `max_length: 1024` reached step 1 but then OOMed on 4xH200
- the repository now includes a helper to normalize mixed canonical JSONL files
  into a uniform `messages`-only dataset for `ms-swift`

Teacher-server rule for external GKD teachers:

- if you use upstream `teacher_model_server` instead of a local
  `teacher_model`, the server must expose OpenAI-compatible `top_logprobs`
- for `gkd_logits_topk: 64`, the teacher server must be started with
  `--max-logprobs 64` or higher
- the repository includes a reusable vLLM teacher template at
  [`../scripts/vllm_teacher_qwen3_235b_tp8.sh`](../scripts/vllm_teacher_qwen3_235b_tp8.sh)
- that helper script is shipped in the public release snapshot

## Secrets Required by Scenario

### Training launch

- `TARGON_API_KEY`
- `TARGON_PROJECT_ID`
- `TARGON_SSH_KEY_UID`
- `HF_TOKEN`
- `WANDB_API_KEY`, unless `training.report_to: none`
### Training artifact or model publishing

- `HF_TOKEN`

### Pure remote execution without training launch

- `TARGON_API_KEY`
- `TARGON_PROJECT_ID`
- `TARGON_SSH_KEY_UID`

Environment loading behavior:

- the launcher checks the current shell first
- missing keys are then backfilled from the repository `.env`
- if the repository `.env` is absent, it also checks a parent-directory `.env`

Default observability behavior:

- training launch defaults to `report_to: wandb`
- the launcher auto-fills `training.wandb_run_name` from `experiment.id` when
  you do not set it explicitly
- to opt out for a specific run, set `training.report_to: none`

See [`../.env.example`](../.env.example) for placeholders.

## Fields You Must Edit

Change at minimum before using the official training config:

- `experiment.id`
- `publish.hub_model_id`
- `publish.private`
- `execution.target.workload_name`
- `execution.target.machine_name`
- `execution.target.public_key` if you do not use `~/.ssh/id_ed25519.pub`

Confirm before launch:

- `dataset.repo_id`
- `dataset.filename`
- `training.model`
- `training.report_to`
- `training.wandb_project`
- `execution.target.resource`
- `execution.resources`

SSH key rule:

- if you pass `TARGON_SSH_KEY_UID`, it must correspond to the same local key
  pair referenced by `execution.target.public_key`

## Validated Behavior

The following behavior has been explicitly validated and is safe to describe as
supported in the docs:

- the training launcher can provision an isolated Targon rental
- the official training launch uses `targon-rental-host`
- a real training run can complete on Targon
- a real bucketed full-SFT launch now completes through the normal training
  launch path and uploads the final artifact to Hugging Face
- a real bucketed LoRA-SFT launch now completes through the normal training
  launch path, with staged adapter continuation and final adapter upload to
  Hugging Face
- a real native `ms-swift` GKD run now completes through the normal training
  launch path without remotely installing `vllm` by hand
- the launcher can create the target Hugging Face model repo when requested
- final training artifacts can be uploaded to either a private or a public
  Hugging Face repo
- the upload path writes a normalized `README.md` with a valid `base_model`
  field

## Post-Launch Commands

Replace `<experiment-id>` with the value you set in the config:

```bash
python3 -m orbit control run status <experiment-id> train
python3 -m orbit control run logs <experiment-id> train --tail 200
python3 -m orbit control run collect <experiment-id> train
```
