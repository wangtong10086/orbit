# Test Runbook

This runbook lists practical validation commands for the current repository
surface. Use it after documentation or runtime-facing changes.

For the conceptual map of which files to inspect and how to interpret them,
start with:

- [debugging.md](debugging.md)
- [logging-and-artifacts.md](logging-and-artifacts.md)
- [nvml-gpu-audit.md](nvml-gpu-audit.md)

The primary documented deployment pattern for this repository is local
`control` plus Targon execution, so this runbook puts the Targon path first.

## 1. CLI Surface

```bash
python3 -m orbit --help
python3 -m orbit control --help
python3 -m orbit worker --help
python3 -m orbit data --help
python3 -m orbit data swe-collect --help
python3 -m orbit data swe-collect evaluate --help
python3 -m orbit data swe-collect synthesize --help
python3 -m orbit data swe-collect prewarm-images --help
python3 -m orbit data swe-collect openenv reset --help
python3 -m orbit data swe-collect openenv state --help
python3 -m orbit data swe-collect openenv checkpoint --help
python3 -m orbit data swe-collect openenv restore --help
python3 -m orbit data swe-collect openenv step --help
python3 -m orbit data swe-collect openenv stop --help
python3 -m orbit remote --help
python3 -m orbit monitor --help
```

Purpose:

- verify root command loading
- verify command-family help remains aligned with docs

## 1a. SWE Collection Surface

Local black-box help:

```bash
python3 -m orbit data swe-collect --help
python3 -m orbit data swe-collect evaluate --help
python3 -m orbit data swe-collect synthesize --help
python3 -m orbit data swe-collect openenv reset --help
python3 -m orbit data swe-collect openenv state --help
python3 -m orbit data swe-collect openenv checkpoint --help
python3 -m orbit data swe-collect openenv restore --help
python3 -m orbit data swe-collect openenv step --help
python3 -m orbit data swe-collect openenv stop --help
```

Expected result:

- the help shows `evaluate`, `synthesize`, and `openenv`
- `evaluate --help` shows upstream repo path/url/ref fields plus
  `agent/model/api_base/api_key`
- `synthesize --help` shows:
  - upstream repo path/url/ref fields
  - `--model --api-base --api-key`
  - `--teacher-model --teacher-api-base --teacher-api-key*`
  - `--reasoning-effort --teacher-reasoning-effort`
  - `--max-root-retries --max-edit-retries`
  - `--transport-only-retries`
- `prewarm-images --help` shows:
  - `--selected-tasks-json`
  - `--cache-dir`
  - `--output`
  - `--image-pull-timeout-secs`
  - `--image-pull-concurrency`
  - `--image-pull-retries`
- `openenv reset --help` shows upstream repo path/url/ref fields and task id
- staged commands such as `sample`, `relabel`, `build-buckets`,
  `train-verifier`, and `smoke` are not part of the active CLI

Real local SWE black-box example:

```bash
python3 -m orbit data swe-collect evaluate \
  --task-file /tmp/orbit-swe-taskfiles/geopy.txt \
  --upstream-repo-path /abs/path/to/affinetes \
  --upstream-ref <exact-affinetes-commit> \
  --agent codex \
  --model <model-id> \
  --api-base https://llm.chutes.ai/v1 \
  --api-key "$CHUTES_API_KEY" \
  --output-dir logs/real-tests/swe-blackbox-local
```

Validation notes:

- inspect `manifests/run.json` to confirm the exact upstream ref, command, and
  per-task raw output paths
- compare `raw/upstream_result.json`, `stdout.log`, and `stderr.log` against a
  direct upstream invocation when validating black-box parity

Real local-or-remote synth example:

```bash
python3 -m orbit data swe-collect synthesize \
  --task-id 19 \
  --upstream-repo-path /abs/path/to/affinetes \
  --upstream-ref <exact-affinetes-commit> \
  --model <student-model> \
  --api-base <student-openai-compatible-base-url> \
  --api-key <student-api-key> \
  --teacher-model gpt-5.4 \
  --teacher-api-base <teacher-openai-compatible-base-url> \
  --teacher-api-key <teacher-api-key> \
  --teacher-reasoning-effort medium \
  --max-steps 8 \
  --max-root-retries 1 \
  --max-edit-retries 1 \
  --output-dir logs/real-tests/swe-synth-run
```

Validation notes:

- inspect `raw/synthesis_events.jsonl` for:
  - `reset`
  - `checkpoint`
  - `model_action`
  - `step`
  - `state`
  - `restore`
- inspect `manifests/synthesis_run.json` for:
  - `student_calls`
  - `teacher_calls`
  - `baseline_checkpoint_id`
  - `edit_checkpoint_id`
  - `latest_changed_files`
  - `final_observation`

Real local-or-remote image prewarm example:

```bash
python3 -m orbit data swe-collect prewarm-images \
  --selected-tasks-json logs/real-tests/swe-qwen36-clean-eval-batch100-20260420/selected_tasks.json \
  --cache-dir /tmp/swe-infinite-cache \
  --output logs/real-tests/swe-qwen36-clean-eval-batch100-20260420/image_prewarm.json
```

Validation notes:

- inspect `image_prewarm.json` for:
  - `unique_image_count`
  - per-image `status`
  - `task_ids`
  - `instance_ids`
- do not launch the batch until every image status is `cached` or `pulled`
- for large benchmark runs, start the run from a fresh output directory that
  copies both `selected_tasks.json` and `image_prewarm.json`

Tracked large-batch launcher example:

```bash
python3 scripts/swe_launch_batch.py \
  --selected-tasks-json logs/real-tests/swe-qwen36-clean-eval-batch100-20260420/selected_tasks.json \
  --image-prewarm-json logs/real-tests/swe-qwen36-clean-eval-batch100-20260420/image_prewarm.json \
  --output-dir logs/real-tests/swe-qwen36-clean-eval-batch100-fastfix-run-20260420/run \
  --upstream-repo-path /root/affinetes-fork \
  --upstream-ref <exact-affinetes-commit> \
  --cache-dir /tmp/swe-infinite-cache \
  --model Qwen/Qwen3.6-35B-A3B \
  --api-base http://127.0.0.1:30001/v1 \
  --api-key dummy \
  --student-log-path /root/logs/sglang-qwen36-95-cg-radix.log \
  --student-ssh-host <student-host> \
  --student-ssh-port <student-ssh-port>
```

Validation notes:

- inspect `run/ready_gate.json` before trusting the run as valid
- inspect `run/campaign_state.json` for:
  - explicit per-task state
  - `started`
  - `completed`
  - `failed_infra`
  - `failed_model`
- inspect `run/campaign_metrics.jsonl` for:
  - `active_rollouts`
  - `active_bootstraps`
  - `h200_running_req`
  - `h200_gen_throughput`
- a task that exits without a normal run manifest should still end up with
  `manifests/synthesis_run.json` carrying:
  - `runtime_bootstrap_failed`
  - `student_transport_failed`
  - `openenv_failed`
  - or `launch_aborted`

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
  --bundle-dir /tmp/personal-project-doc-runbook \
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
- while bucket splitting is still running, operators can inspect
  `runtime/bucketed/progress.json` for `completed_batches`,
  `total_rows_written`, and `rows_per_second`
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

Production offline-topk collection:

```bash
bash examples/official/sampling/collect-offline-topk-canonical.sh
```

Expected result:

- the source dataset is filtered to `<= 32k`
- prepared rows are split into `b8 / b16 / b32`
- collection writes incremental `part-*.jsonl` files per bucket
- each uploaded part lands under `offline_topk/canonical/<bucket>/`
- `collection_manifest.json` reflects completed rows and uploaded parts

## 8. External Teacher Server Logprob Check

For `gkd_logits_topk: 64`, confirm the teacher server is started with
`--max-logprobs 64` or higher before launching training.

Launch template:

```bash
bash scripts/vllm_teacher_qwen3_235b_tp8.sh
```

## 9. Experimental MemoryGym RL Smoke

Current status:

- command shape is now defined in-repo
- real validation exists, but the profile-based server path is still failing at
  upstream external-vLLM communicator initialization

Launch command:

```bash
python3 -m orbit control launch train \
  --config examples/official/training/targon-qwen3-8b-memorygym-grpo-smoke.yaml
```

Inspection examples:

```bash
python3 -m orbit control run status official-qwen3-8b-memorygym-grpo-smoke train
python3 -m orbit control run logs official-qwen3-8b-memorygym-grpo-smoke train --tail 200
python3 -m orbit control run collect official-qwen3-8b-memorygym-grpo-smoke train
```

Preconditions for the first real run:

- provision a fresh isolated `h200-small` rental
- ensure `repos/MemoryGym` exists locally before launch
- verify the remote runtime can import:
  - `swift`
  - `vllm`
  - `memorygym` after the staged package install step

Expected smoke artifacts:

- `artifacts/runtime-precheck.log`
- `artifacts/nvml-audit.jsonl`
- `artifacts/nvml-audit.log`
- `artifacts/rollout.log`
- `artifacts/training.log`
- `artifacts/checkpoints`

Expected smoke behavior:

- `training.profile_id` resolves the backend/env-pack/runtime metadata before
  submit
- the training bundle stages the local `ms-swift` fork and remote runtime logs
  show that `swift` imports resolve from the staged fork path
- confirm this by checking `runtime-precheck.log` for a line like:
  `swift runtime import ok: version=... path=.../bundle/inputs/runtime-swift-fork-ms_swift_fork/swift/__init__.py`
- `swift rollout` starts in server mode and passes health checks
- `swift rlhf` connects to that rollout server through the normal
  `training_launch` path
- the bundle still stages both migration inputs:
  - `scripts/memorygym_ms_swift_plugin.py`
  - `repos/MemoryGym`
  - `packages/env_memorygym`

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

## 10. Secondary Local Host / Docker Debugging

Use the local worker flows when you want to debug a bundle locally rather than
validate the primary Targon path.

Read [logging-and-artifacts.md](logging-and-artifacts.md) before running these
commands if you need a quick reminder of which files to inspect afterward.

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
then waits for public `CI`, `Docs`, and `Docker` on `wangtong10086/ORBIT`.

Notes:

- `packages/**` changes now also trigger the private `Docker` and
  `publish-public` workflows automatically
- the exported public snapshot includes `packages/` because the public Docker
  build consumes those sources directly

## 11. MemoryGym 32B Aligned Snapshot (2026-04-11)

Goal:

- keep training behavior strictly aligned with online evaluation
- verify reward is non-zero before long production run

Machine and run context:

- machine: `mgym32-aligned-0412` (`72.46.85.157:30282`), 8xH200
- experiment: `memorygym-32b-grpo-aligned-0412b`
- model: `momentspeed/affine-qwen3-32b-v239-ckpt600`

Validated alignment settings:

- `enable_thinking: false`
- `completion_length_limit_scope: per_round`
- `max_completion_length: 2048`
- `context_manager: memorygym_redact`
- `tier: standard`
- `max_turns: 256`

Key fixes already applied:

- fixed plugin registration mismatch by deploying updated `orbit_env_memorygym`
- fixed launch crash from online wandb mode by forcing `WANDB_MODE=offline`
- fixed earlier OOM by reducing `max_completion_length: 4096 -> 2048`
- added allocator fragmentation mitigation:
  - `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`
  - `vllm_gpu_memory_utilization: 0.15 -> 0.10`

Current blocker:

- rental machine became temporarily unreachable (`ssh: connection refused`) while
  validating the latest restart attempt

Resume checklist:

```bash
# 1) reconnect and inspect status
ssh -o StrictHostKeyChecking=no -i ~/.ssh/id_ed25519 -p 30282 root@72.46.85.157

# 2) check whether training is still running and whether step 1 completed
tail -50 /root/orbit-execution/memorygym-32b-grpo-aligned-0412b/bundle/artifacts/training.log
grep -E "OOM|OutOfMemory|Traceback|step" /root/orbit-execution/memorygym-32b-grpo-aligned-0412b/bundle/artifacts/training.log | tail -40

# 3) verify reward metrics
cat /root/orbit-execution/memorygym-32b-grpo-aligned-0412b/bundle/artifacts/checkpoints/*/logging.jsonl | tail -20
```
