# Official Remote Examples

This document covers the official remote examples for ORBIT. It is
deliberately centered on Targon because the primary documented use case for this
project is local control plus remote execution on Targon rentals.

## Official Targon Training Example

Use this config as the official production-style training example:

- [`../examples/official/training/targon-qwen3-32b-full-sft.yaml`](../examples/official/training/targon-qwen3-32b-full-sft.yaml)

Launch command:

```bash
python3 -m orbit control launch train \
  --config examples/official/training/targon-qwen3-32b-full-sft.yaml
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

- the launcher currently downloads or locates the dataset first, then copies it
  into the execution bundle
- training runs therefore use a local bundle dataset path at runtime, not a
  direct remote dataset id

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
