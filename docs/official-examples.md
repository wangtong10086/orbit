# Official Examples

This document covers the repository's supported example workflows. It explains
which example is the recommended starting point. It does not restate the full
CLI or architecture reference.

## Current Official Training Example

Use this config as the supported one-command training example:

- [`../examples/official/training/targon-qwen3-32b-full-sft.yaml`](../examples/official/training/targon-qwen3-32b-full-sft.yaml)

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

## Required Secrets

Put secrets in `.env` or your shell before launch. Do not commit real tokens in
the example config.

Minimum variables:

- `HF_TOKEN`
- `TARGON_API_KEY`
- `TARGON_PROJECT_ID`
- `TARGON_SSH_KEY_UID`

See [`../.env.example`](../.env.example) for placeholders.

## Launch Command

```bash
python -m forge control launch train \
  --config examples/official/training/targon-qwen3-32b-full-sft.yaml
```

## Fields To Edit Before Use

Change at minimum:

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
- `execution.target.resource`
- `execution.resources`

SSH key rule:

- if you pass `TARGON_SSH_KEY_UID`, it must correspond to the same local key pair
  referenced by `execution.target.public_key`

## Hugging Face Upload Behavior

The official launch path supports automatic post-training upload to either a
private or a public Hugging Face model repo.

Use these fields:

- `publish.push_to_hub: true`
- `publish.hub_model_id: <your-user-or-org>/<repo-name>`
- `publish.create_repo: true`
- `publish.private: true` for a private repo, or `false` for a public repo

Validated behavior:

- the launcher creates the model repo before submission when requested
- training completes first
- the final adapter/checkpoint artifacts are uploaded after training finishes
- the uploaded repo includes a normalized `README.md` with a valid
  `base_model` field

Required secret:

- `HF_TOKEN` must have permission to create and write the target model repo

## Post-Launch Commands

```bash
python -m forge control run status official-qwen3-32b-swe-infinite-full-sft train
python -m forge control run logs official-qwen3-32b-swe-infinite-full-sft train --tail 200
python -m forge control run collect official-qwen3-32b-swe-infinite-full-sft train
```
