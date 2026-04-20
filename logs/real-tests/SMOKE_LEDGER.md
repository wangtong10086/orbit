# Targon Smoke Ledger

This file is the fixed cross-run ledger for Targon smoke and end-to-end validation rentals.

Rules:
- add the smoke here before launch
- update the status when the run starts
- update the outcome after logs and artifacts are checked
- terminate failed or no-longer-needed rentals promptly
- if a rental is intentionally kept alive, record the reason and owner

## 2026-04-10T14:13:00Z memorygym-8b-colocate-20260410t
- purpose: reproduce the 2xH200 colocate OOM and capture the cause in `nvml-audit.jsonl`
- config: logs/real-tests/memorygym-8b-colocate-20260410/launch-config-0410t.yaml
- workload: pending
- machine: pending
- host: pending
- status: planned
- cleanup: current turn
- notes: prelaunch cleanup removed stale smoke rentals `mgym32cspo-0409c` and `mgym8bclct-0410s`

## 2026-04-10T14:21:30Z memorygym-8b-colocate-20260410u
- purpose: rerun the 2xH200 colocate recipe after env-name and completion-context fixes so the original OOM can be captured with `nvml-audit.jsonl`
- config: logs/real-tests/memorygym-8b-colocate-20260410/launch-config-0410u.yaml
- workload: wrk-6kzndw8vpy6b
- machine: mgym8bclct-0410u
- host: 72.46.85.157:32327
- status: failed-cleaned
- cleanup: `orbit control run terminate memorygym-8b-colocate-20260410u train`
- notes: train progressed back into the high-memory colocate path and `nvml-audit.jsonl` captured worker peaks of ~`54.9 GiB` / `55.1 GiB`, but the run still failed before OOM because the image-installed `orbit_env_memorygym` package only exposed `memorygym_env`, not the `MEMORYGYM` alias expected by the dataset rows

## 2026-04-10T14:28:30Z memorygym-8b-colocate-20260410v
- purpose: rerun the 2xH200 colocate smoke with `32k` context, `4k` completion, `gradient_accumulation_steps=4`, `per_device_train_batch_size=1`, and `gradient_checkpointing=true`
- config: logs/real-tests/memorygym-8b-colocate-20260410/launch-config-0410v.yaml
- workload: wrk-8xzpsjbywwpx
- machine: mgym8bclct-0410v
- host: 72.46.85.157:31594
- status: failed-cleaned
- cleanup: `orbit control run terminate memorygym-8b-colocate-20260410v train`
- notes: real failure happened before rollout/oom because TRL rejected the batch geometry for GRPO: `generation_batch_size (2) must be divisible by num_generations (4)`; NVML audit still recorded the early startup memory ramp before shutdown

## 2026-04-10T14:39:30Z memorygym-8b-colocate-20260410w
- purpose: rerun the `32k`/`4k` dual-H200 colocate smoke with `per_device_train_batch_size=2` so GRPO clears the generation-batch divisibility check
- config: logs/real-tests/memorygym-8b-colocate-20260410/launch-config-0410w.yaml
- workload: wrk-9djrtr4wssht
- machine: mgym8bclct-0410w
- host: 72.46.85.157:30820
- status: failed-cleaned
- cleanup: `orbit control run terminate memorygym-8b-colocate-20260410w train`
- notes: real logs were produced; the run cleared the GRPO divisibility gate and ramped memory to ~`54.9 GiB` / `55.1 GiB` per worker, but still failed before OOM on the same env alias mismatch: `Environment 'MEMORYGYM' not found`

## 2026-04-10T14:50:30Z memorygym-8b-colocate-20260410x
- purpose: rerun the `32k`/`4k` dual-H200 colocate smoke after fixing the external plugin shim to prefer the staged env-pack source
- config: logs/real-tests/memorygym-8b-colocate-20260410/launch-config-0410x.yaml
- workload: wrk-po9esp2sxxxx
- machine: mgym8bclct-0410x
- host: 72.46.85.157:32290
- status: failed-cleaned
- cleanup: `orbit control run terminate memorygym-8b-colocate-20260410x train`
- notes: the shim change was insufficient; real logs again failed on `Environment 'MEMORYGYM' not found`, while NVML showed the same ~`54.9 GiB` / `55.1 GiB` worker peak before shutdown

## 2026-04-10T15:00:30Z memorygym-8b-colocate-20260410y
- purpose: rerun the `32k`/`4k` dual-H200 colocate smoke after normalizing env names inside the forked GYMScheduler
- config: logs/real-tests/memorygym-8b-colocate-20260410/launch-config-0410y.yaml
- workload: wrk-fze5ay6itaa2
- machine: mgym8bclct-0410y
- host: 72.46.85.157:31119
- status: failed-cleaned
- cleanup: `orbit control run terminate memorygym-8b-colocate-20260410y train`
- notes: the env alias mismatch disappeared and the run stayed live long enough to confirm real dual-H200 execution, but it never produced `logging.jsonl`; after ~10 minutes at `Train: 0/10`, both ranks hit an NCCL collective watchdog timeout with mismatched `_ALLGATHER_BASE` input sizes

## 2026-04-10T15:15:30Z memorygym-8b-colocate-20260410z
- purpose: rerun the same `32k`/`4k` dual-H200 colocate smoke without `FSDP2` so the next boundary is DDP plus colocate TP=2
- config: logs/real-tests/memorygym-8b-colocate-20260410/launch-config-0410z.yaml
- workload: wrk-fcu0axcpie8o
- machine: mgym8bclct-0410z
- host: 72.46.85.157:30722
- status: failed-cleaned
- cleanup: `orbit control run terminate memorygym-8b-colocate-20260410z train`
- notes: removing `FSDP2` did not change the failure mode; the run reached the same first-step boundary and timed out on `_ALLGATHER_BASE` after ~10 minutes, with mismatched `NumelIn` values across ranks

## 2026-04-10T15:31:30Z memorygym-8b-colocate-20260410aa
- purpose: rerun the same `32k`/`4k` dual-H200 colocate smoke with `vllm_tensor_parallel_size=1` to test whether TP collectives are the first-step failure source
- config: logs/real-tests/memorygym-8b-colocate-20260410/launch-config-0410aa.yaml
- workload: wrk-kxxvcb2bxqkm
- machine: mgym8bclct-0410aa
- host: 72.46.85.157:31524
- status: failed-cleaned
- cleanup: `orbit control run terminate memorygym-8b-colocate-20260410aa train`
- notes: lowering `vllm_tensor_parallel_size` from `2` to `1` removed the previous `_ALLGATHER_BASE` timeout, but the run failed earlier during vLLM KV-cache initialization with `ValueError: No available memory for the cache blocks`

## 2026-04-10T15:40:30Z memorygym-8b-colocate-20260410ab
- purpose: rerun the same `32k`/`4k` dual-H200 colocate smoke with `TP=2` and `vllm_gpu_memory_utilization=0.4`
- config: logs/real-tests/memorygym-8b-colocate-20260410/launch-config-0410ab.yaml
- workload: wrk-wlecdtuu8d9h
- machine: mgym8bclct-0410ab
- host: 72.46.85.157:30816
- status: failed-cleaned
- cleanup: `orbit control run terminate memorygym-8b-colocate-20260410ab train`, then direct `DELETE /tha/v2/workloads/wrk-wlecdtuu8d9h` after verifying the rental was still live in Targon
- notes: this run moved past the `TP=1` KV-cache startup failure and held both GPUs around `78-79 GiB`, but it still never produced `logging.jsonl`; after about 10 minutes at `Train: 0/10`, the dual-rank colocate path hit the same `_ALLGATHER_BASE` NCCL watchdog timeout with mismatched `NumelIn` values across ranks

## 2026-04-10T16:25:00Z memorygym-8b-colocate-20260410ac
- purpose: rerun the same `32k`/`4k` dual-H200 colocate smoke after defaulting WandB back on, adding local profiling logs, and changing the TP=2 colocate rollout path so only the TP-group leader drives inference before broadcasting outputs
- config: logs/real-tests/memorygym-8b-colocate-20260410/launch-config-0410ac.yaml
- workload: wrk-r35o60mr4k6y
- machine: mgym8bclct-0410ac
- host: 72.46.85.157:32313
- status: failed-cleaned
- cleanup: `orbit control run terminate memorygym-8b-colocate-20260410ac train`, then direct `DELETE /tha/v2/workloads/wrk-r35o60mr4k6y`; post-cleanup active rental check is empty
- notes: this rerun produced `training.log`, a live local `wandb` run, profiling stage logs, and the new TP-group leader marker `stage=colocate_rollout leader_rank=0 all_input_lengths=[2, 2] total_requests=4`, but still never created `logging.jsonl`; after ~10 minutes inside `GRPOTrainer.generate`, the failure changed from the old anonymous `_ALLGATHER_BASE` timeout to a more specific `ProcessGroupNCCL` watchdog timeout on `OpType=BROADCAST, NumelIn=1`

## 2026-04-10T17:05:00Z memorygym-8b-colocate-20260410ad
- purpose: single-H200 colocate baseline after the TP-group driver refactor, to prove the new fork path did not regress single-rank multi-turn GRPO
- config: logs/real-tests/memorygym-8b-colocate-20260410/launch-config-0410ad.yaml
- workload: wrk-87144fkyl9jm
- machine: mgym8bclct-0410ad
- host: 72.46.85.157:31028
- status: succeeded-cleaned
- cleanup: `orbit control run terminate memorygym-8b-colocate-20260410ad train`, then direct `DELETE /tha/v2/workloads/wrk-87144fkyl9jm`; post-cleanup active rental check is empty
- notes: baseline passed with real `10/10` training, `logging.jsonl`, checkpoint-5/checkpoint-10, and local `wandb`; downstream `orbit control run collect` exposed a separate execution-layer issue because the remote workspace no longer existed by collection time

## 2026-04-10T17:06:00Z memorygym-8b-colocate-20260410ae
- purpose: short-context 2xH200 TP=2 smoke after the TP-group driver refactor, to validate all-rank compute plus leader-only env control before retrying `32k`/`4k`
- config: logs/real-tests/memorygym-8b-colocate-20260410/launch-config-0410ae.yaml
- workload: wrk-0sumvqvsrqw1
- machine: mgym8bclct-0410ae
- host: 72.46.85.157:31486
- status: failed-cleaned
- cleanup: `orbit control run terminate memorygym-8b-colocate-20260410ae train`, then direct `DELETE /tha/v2/workloads/wrk-0sumvqvsrqw1`; post-cleanup active rental check is empty
- notes: this run finally produced `logging.jsonl` and a local `wandb` run on the short-context `2xH200` recipe, proving the TP-group driver fix moved the dual-card path past the old NCCL rollout timeout; however `logging.jsonl` still stayed at `global_step: 0` because the first backward pass failed on both ranks with `RuntimeError: local_used_map_tmp.is_pinned() INTERNAL ASSERT FAILED`

## 2026-04-10T17:45:00Z memorygym-8b-colocate-20260410af
- purpose: rerun the short-context 2xH200 TP=2 colocate smoke after forcing `ddp_find_unused_parameters=false` and `ddp_broadcast_buffers=false` under gradient checkpointing in the local fork
- config: logs/real-tests/memorygym-8b-colocate-20260410/launch-config-0410af.yaml
- workload: wrk-uu33unxmhgiq
- machine: mgym8bclct-0410af
- host: 72.46.85.157:31845
- status: succeeded-cleaned
- cleanup: local launch process killed after evidence capture, then direct `DELETE /tha/v2/workloads/wrk-uu33unxmhgiq`; post-cleanup active rental check is empty
- notes: this rerun completed the first real short-context dual-card step on `2xH200` with `TP=2`; `training.log`, local `wandb`, and `logging.jsonl` all advanced past the old `local_used_map_tmp.is_pinned()` boundary and recorded `global_step/max_steps: 1/10`

## 2026-04-10T17:52:00Z memorygym-8b-colocate-20260410ag
- purpose: rerun the real `32k/4k` 2xH200 TP=2 colocate recipe after the same DDP gradient-checkpointing defaults fix passed the short-context smoke
- config: logs/real-tests/memorygym-8b-colocate-20260410/launch-config-0410ag.yaml
- workload: wrk-jbbhmiroeymb
- machine: mgym8bclct-0410ag
- host: 72.46.85.157:31964
- status: failed-cleaned
- cleanup: direct `DELETE /tha/v2/workloads/wrk-jbbhmiroeymb`; post-cleanup active rental check is empty
- notes: the `32k/4k` high-context recipe did not reproduce the short-context `local_used_map_tmp.is_pinned()` backward failure, but it still timed out on the old `_ALLGATHER_BASE` collective after ~10 minutes with mismatched `NumelIn` values (`303872` vs `227904`) across ranks

## 2026-04-10T18:16:00Z memorygym-8b-colocate-20260410ah
- purpose: rerun the short-context 2xH200 TP=2 colocate smoke after switching TP>1 inference to leader-only request submission plus all-rank engine stepping
- config: logs/real-tests/memorygym-8b-colocate-20260410/launch-config-0410ah.yaml
- workload: wrk-nwznw2o532bu
- machine: mgym8bclct-0410ah
- host: 72.46.85.157:30972
- status: failed-cleaned
- cleanup: direct `DELETE /tha/v2/workloads/wrk-nwznw2o532bu`; post-cleanup active rental check is empty
- notes: the new TP-group path was wired into real training and created local `wandb` plus `logging.jsonl`, but failed immediately because `_engine_infer_tp_group` referenced `dist` without importing `torch.distributed as dist`

## 2026-04-10T18:17:00Z memorygym-8b-colocate-20260410ai
- purpose: rerun the real `32k/4k` 2xH200 TP=2 colocate recipe after the same leader-submit all-rank-step fix passes the short-context smoke
- config: logs/real-tests/memorygym-8b-colocate-20260410/launch-config-0410ai.yaml
- workload: pending
- machine: pending
- host: pending
- status: planned
- cleanup: current turn
- notes: do not launch until `0410ah` is closed and cleaned

## 2026-04-10T18:27:00Z memorygym-8b-colocate-20260410aj
- purpose: retry the short-context 2xH200 TP=2 colocate smoke after fixing the missing `dist` import in `_engine_infer_tp_group`
- config: logs/real-tests/memorygym-8b-colocate-20260410/launch-config-0410aj.yaml
- workload: wrk-63lgg9f7lxhe
- machine: mgym8bclct-0410aj
- host: 72.46.85.157:31599
- status: failed-cleaned
- cleanup: `./.venv/bin/python -m orbit control run terminate memorygym-8b-colocate-20260410aj train`, then direct `DELETE /tha/v2/workloads/wrk-63lgg9f7lxhe`; post-cleanup active rental check is empty in `logs/real-tests/memorygym-8b-colocate-20260410/active-rentals-after-0410aj-cleanup.txt`
- notes: this rerun proved the missing `dist` import was fixed and that the new path creates local `wandb`, `training.log`, `nvml-audit.jsonl`, and `args.json`, but it still never wrote `logging.jsonl`; the first rollout stalled after leader submit on `request_lengths=[4096, 4096, 4096, 4096]` and failed on a TP-group `ProcessGroupNCCL` watchdog timeout for `OpType=BROADCAST, NumelIn=1`, so the dual-rank colocate synchronization bug remains

## 2026-04-10T14:04:14Z memorygym-8b-colocate-20260410s
- purpose: validate NVML audit starts before any GPU-consuming training process
- config: logs/real-tests/memorygym-8b-colocate-20260410/launch-config-0410p.yaml
- workload: wrk-aboknt6uvc9u
- machine: mgym8bclct-0410s
- host: 72.46.85.157:32693
- status: succeeded-cleaned
- cleanup: `orbit control run terminate memorygym-8b-colocate-20260410s train`
- notes: `nvml-audit.jsonl` exists and records empty-GPU samples before trainer PID 889 / worker PIDs 974 and 975 appear

## 2026-04-10T13:24:18Z memorygym-8b-colocate-20260410q
- purpose: first real NVML-audit rerun on the known-OOM 2xH200 recipe
- config: logs/real-tests/memorygym-8b-colocate-20260410/launch-config-0410p.yaml
- workload: wrk-fvxw1mhbm8qm
- machine: mgym8bclct-0410q
- status: failed-cleaned
- cleanup: direct `DELETE /tha/v2/workloads/wrk-fvxw1mhbm8qm`
- notes: control-plane launch stalled at `provisioning_target`; no train run handle was recorded

## 2026-04-10T13:55:54Z memorygym-8b-colocate-20260410r
- purpose: retry real NVML-audit rerun after adding runtime `nvidia-ml-py` fallback
- config: logs/real-tests/memorygym-8b-colocate-20260410/launch-config-0410p.yaml
- workload: wrk-gasiub9ir0iq
- machine: mgym8bclct-0410r
- status: failed-cleaned
- cleanup: direct `DELETE /tha/v2/workloads/wrk-gasiub9ir0iq`
- notes: control-plane launch stalled at `provisioning_target`; no train run handle was recorded

## 2026-04-11T13:55:00Z qwen3-32b-offline-topk-full-gkd-20260411-4xb
- purpose: start real offline-topk full-parameter GKD on collected canonical data using the merged public HF dataset and verify the bucketed 4xH200 launch reaches real training startup
- config: /tmp/qwen3-32b-offline-topk-full-gkd-20260411-4x.yaml
- workload: wrk-1lowv04ufuwu
- machine: q32offgkd-20260411d-h200x4
- host: 72.46.85.157:30317
- status: running
- cleanup: current turn
- notes: uses `waston10086/orbit-offline-topk-canonical-qwen3-235b-fp8-20260411-public` as the dataset source, binds the already-registered SSH machine `q32offgkd-20260411d-h200x4`, launched as experiment `qwen3-32b-offline-topk-full-gkd-20260411-4xc`, submitted real run `605`, and has already entered remote bucket splitting inside `/root/orbit-execution/qwen3-32b-offline-topk-full-gkd-20260411-4xc`

## 2026-04-11T14:48:08Z qwen3-32b-offline-topk-full-gkd-20260411e

## 2026-04-17T05:48:31Z swe-mini-smoke-20260417a
- purpose: run a real small-scale remote SWE MiniSWE collection smoke on a fresh isolated Targon rental, pulling tasks directly from R2 and collecting at least one canonical success
- config: logs/real-tests/swe-collect-smoke-20260417/README.txt
- workload: wrk-9hx2flmrmgi4
- machine: swe-mini-smoke-20260417a
- host: 72.46.85.157:31727
- status: failed-cleaned
- cleanup: direct `DELETE /tha/v2/workloads/wrk-sn5nx9j4ioba` for the first sshd-path attempt, then direct `DELETE /tha/v2/workloads/wrk-9hx2flmrmgi4` for the dropbear-path retry
- notes: first fresh-rental attempt `wrk-sn5nx9j4ioba` created and deployed but remained stuck at `provisioning` with DIRECT port `31552`; second retry `wrk-9hx2flmrmgi4` used a dropbear-only init command, reached `running`, exposed DIRECT port `31727`, but repeated SSH probes still returned `connection refused` after a full startup window; no remote collector command could be launched, so no canonical row or `swe-sync` import exists for this format

## 2026-04-17T05:48:31Z swe-codex-smoke-20260417b
- purpose: run a real small-scale remote SWE Codex collection smoke on a fresh isolated Targon rental, pulling tasks directly from R2 and collecting at least one canonical success
- config: logs/real-tests/swe-collect-smoke-20260417/README.txt
- workload: wrk-k7v8w9zqb4a7
- machine: swe-codex-smoke-20260417b
- host: 72.46.85.157:31667
- status: failed-cleaned
- cleanup: direct `DELETE /tha/v2/workloads/wrk-6soqffr5j3qc` for the first sshd-path attempt, then direct `DELETE /tha/v2/workloads/wrk-k7v8w9zqb4a7` for the dropbear-path retry
- notes: first fresh-rental attempt `wrk-6soqffr5j3qc` created and deployed but remained stuck at `provisioning` with DIRECT port `30552`; second retry `wrk-k7v8w9zqb4a7` used a dropbear-only init command, reached `running`, exposed DIRECT port `31667`, but repeated SSH probes still returned `connection refused` after a full startup window; the original teacher workload `sw32kdx` also disappeared mid-run and later returned HTTP 404, while the configured fallback `OPENAI_BASE_URL` returned HTTP 400 on `/models`, so the teacher endpoint assumption was not stable either

## 2026-04-17T06:09:59Z swe-cpu-smoke-preflight-20260417c
- purpose: verify whether the requested CPU-path smoke can start with `.env` `OPENAI_API_KEY` / `OPENAI_BASE_URL` as teacher endpoint and model `robert131004/affine-5Dh8N4SChjXxbGEV27pnaB9tC8QZ4eYFBuq95TgjQZRpZitj`
- config: logs/real-tests/swe-collect-smoke-20260417/README.txt
- workload: none
- machine: none
- host: none
- status: failed-cleaned
- cleanup: no Targon workload launched; active workload list remained empty
- notes: before launching a CPU workload, a direct teacher preflight request to `${OPENAI_BASE_URL}/chat/completions` with the requested model failed with HTTP 400 `SETTLEMENT_UNKNOWN_MODEL`; the current collector has no separate `student_model` field, so this model id would be used as the active teacher-side model selection for requests against the endpoint

## 2026-04-12T17:50:00Z qwen3-32b-online-gkd-20260412a
- purpose: switch the 32B full-parameter canonical distillation path from offline-topk back to online external-teacher GKD, using the live `qwen3-235b-teacher-model` vLLM server and a fresh isolated 8xH200 student rental
- config: /tmp/qwen3-32b-online-gkd-20260412a-8x.yaml
- workload: wrk-4myvzgbhambq
- machine: q32onlgkd-20260412a-h200x8
- host: 72.46.85.157:31109
- status: failed-cleaned
- cleanup: direct `DELETE /tha/v2/workloads/wrk-4myvzgbhambq`, local launch process stopped, experiment lock removed
- notes: current 8xH200 student rental `wrk-1amtnp63i79a` failed the reuse gate because stale `torchrun/pt_elastic` processes remained active and GPU memory was not fully released; the first fresh isolated 8xH200 provisioning attempt stalled in `provisioning` with no SSH readiness or state timestamp progress

## 2026-04-12T17:57:30Z qwen3-32b-online-gkd-20260412b
- purpose: retry the 32B full-parameter canonical online external-teacher GKD launch by provisioning the 8xH200 rental first, then launching against a registered machine
- config: /tmp/qwen3-32b-online-gkd-20260412b-8x.yaml
- workload: wrk-e6u8txrd2j6a
- machine: q32onlgkd-20260412b-h200x8
- host: 72.46.85.157:31194
- status: failed-cleaned
- cleanup: direct `DELETE /tha/v2/workloads/wrk-e6u8txrd2j6a`
- notes: the second 8xH200 provisioning attempt also stalled before SSH readiness; this exposed that the rental init helper was still doing `apt-get + dropbear` even though the training image already ships `openssh-server`

## 2026-04-12T18:03:30Z qwen3-32b-online-gkd-20260412c
- purpose: retry the 32B canonical online external-teacher GKD launch after switching Targon SSH rental init to use the image's built-in `sshd` instead of `apt-get + dropbear`
- config: /tmp/qwen3-32b-online-gkd-20260412c-8x.yaml
- workload: wrk-e0ut1hpu5vs5
- machine: q32onlgkd-20260412c-h200x8
- host: 72.46.85.157:31589
- status: failed-cleaned
- cleanup: direct `DELETE /tha/v2/workloads/wrk-e0ut1hpu5vs5`
- notes: provisioning reached `running`, but container logs showed repeated `chroot(\"/run/sshd\"): Operation not permitted [preauth]`; the SSH init path needs `UsePrivilegeSeparation=no`

## 2026-04-12T18:07:30Z qwen3-32b-online-gkd-20260412d
- purpose: retry the 32B canonical online external-teacher GKD launch after disabling the OpenSSH preauth sandbox in the rental init helper
- config: /tmp/qwen3-32b-online-gkd-20260412d-8x.yaml
- workload: wrk-tsqlycefqyha
- machine: q32onlgkd-20260412d-h200x8
- host: 72.46.85.157:30660
- status: running-followup
- cleanup: current turn
- notes: this retry keeps the same teacher endpoint and dataset, and only changes the SSH rental bootstrap flags; direct SSH and `nvidia-smi` on the fresh 8xH200 machine are now working

## 2026-04-14T04:18:17Z qwen3-32b-kl-bench-20260414a
- purpose: compare the latest saved full-8k online-GKD checkpoint against base `Qwen/Qwen3-32B` on the KL benchmark with `task_id=1..200`
- config: logs/real-tests/qwen3-32b-kl-bench-20260414/README.txt
- workload: `wrk-jjmimbg6yikd` (base), `wrk-g1c0i7icxhp1` (candidate)
- machine: `q32kl-20260414f-base`, `q32kl-20260414f-cand`
- host: `72.46.85.157:32511`, `72.46.85.157:31503`
- status: succeeded-cleaned
- cleanup: direct `DELETE /tha/v2/workloads/wrk-jjmimbg6yikd` and `DELETE /tha/v2/workloads/wrk-g1c0i7icxhp1`
- notes: initial `h200-medium` and early `h200-small` attempts stalled or hit `sshd` preauth bootstrap issues; final successful eval used two isolated `h200-small` rentals with explicit `authorized_keys + dropbear` bootstrap; candidate was evaluated from public HF repo `waston10086/qwen3-32b-online-gkd-8k-checkpoint-5000-public-20260414`; base scored `0.4866` mean KL score while latest `checkpoint-5000` scored `0.0247`, so the latest candidate still regresses against base

## 2026-04-13T06:41:00Z qwen3-32b-kl-bench-20260413a
- purpose: benchmark the 200-step online-GKD checkpoint against base `Qwen/Qwen3-32B` on the `affinetes` distill KL environment using the same task set on a fresh isolated 2xH200 rental
- config: logs/real-tests/qwen3-32b-kl-bench-20260413/README.txt
- workload: wrk-ibegtkpb0iqv
- machine: q32kl-20260413a-h200x2
- host: 72.46.85.157:31794
- status: failed-cleaned
- cleanup: current turn
- notes: rental reached `running`, but workload logs show `sshd` repeatedly failing with `chroot(\"/run/sshd\"): Operation not permitted [preauth]`; workload deleted and replaced with a forced-dropbear retry

## 2026-04-13T08:40:00Z qwen3-32b-kl-bench-20260413b
- purpose: retry the KL benchmark smoke on a fresh isolated 2xH200 rental using forced `dropbear` SSH bootstrap instead of the image `sshd`
- config: logs/real-tests/qwen3-32b-kl-bench-20260413/README.txt
- workload: wrk-mzi73hwc1eg6
- machine: q32kl-20260413b-h200x2
- host: 72.46.85.157:31099
- status: succeeded-cleaned
- cleanup: current turn
- notes: same benchmark target and task-id plan as `20260413a`, only rental SSH bootstrap changed; on `task_id=1..20`, base `Qwen/Qwen3-32B` scored `0.2232` mean KL score while the 200-step candidate scored `0.0267`, so the candidate did not improve on this benchmark; rental terminated after artifact capture

## 2026-04-13T09:40:00Z qwen3-32b-kl-bench-20260413c
- purpose: rerun the same KL benchmark on a fresh isolated 2xH200 rental with `task_id=1..200` to check whether the `1..20` regression result was sampling noise or remains stable
- config: logs/real-tests/qwen3-32b-kl-bench-20260413/README.txt
- workload: wrk-symt8eta84pp
- machine: q32kl-20260413c-h200x2
- host: 72.46.85.157:30975
- status: succeeded-cleaned
- cleanup: current turn
- notes: on `task_id=1..200`, base `Qwen/Qwen3-32B` scored `0.4866` mean KL score while the 200-step candidate scored `0.0787`; this confirms the earlier `1..20` regression was not sampling noise; rental terminated after artifact capture

## 2026-04-17T07:20:00Z swe-five-stage-smoke-20260417
- purpose: real local CPU smoke for the new five-stage SWE collection pipeline using real R2 tasks, Chutes student sampling, offline teacher critique, and staged bucket export
- config: logs/real-tests/swe-five-stage-smoke-20260417/README.txt
- runtime: local CPU + Docker
- status: succeeded
- cleanup: no remote rentals created; local artifacts retained under `logs/real-tests/swe-five-stage-smoke-20260417/`
- notes: MiniSWE task `2` and Codex task `3` both produced non-empty raw trajectories, failure-point relabels, critiques, `B/C/V` buckets, and verifier rows; no real A-bucket success was sampled on the chosen one-step budget; the smoke also exposed and fixed a real Codex protocol bug (`tools` duplicated inside the system message) plus append-only artifact rebuild issues for relabel/buckets/manifests

## 2026-04-17T10:40:00Z swe-cascade-smoke-20260417
- purpose: real local CPU smoke for the revised hidden-oracle + rubric + cascade-search SWE strategy, including sample-level unique ids and near-miss-only teacher repair
- config: logs/real-tests/swe-cascade-smoke-20260417/README.txt
- runtime: local CPU + Docker
- status: succeeded
- cleanup: no remote rentals created; local artifacts retained under `logs/real-tests/swe-cascade-smoke-20260417/`
- notes: MiniSWE task `2` produced hidden oracle, issue rubric, localization shortlist, patch plan, raw trajectory, near-miss repair record, `B/C/V` buckets, and verifier row under sample id `ajvb__kala-202::loc1::patch1::r1`; Codex task `3` produced hidden oracle, rubric, shortlist artifacts, raw trajectory, failure point, and verifier row under sample id `grovesNL__glow-72::loc1::patch1::r1`, but no repair record because the branch did not meet the near-miss gate; this smoke also exposed and fixed two runtime issues: long student responses causing timeout during realization, and Codex plain-text replies without tool calls

## 2026-04-17T13:20:00Z swe-scale-search-20260417
- purpose: expand cascade-search budgets and test whether the revised method can sample at least one verified-correct trajectory on real tasks
- config: logs/real-tests/swe-scale-search-20260417/README.txt
- runtime: local CPU + Docker
- status: completed-no-success
- cleanup: no remote rentals created; local artifacts retained under `logs/real-tests/swe-scale-search-20260417/`
- notes: three expanded searches were run with `temps=0.2,0.5`, `localization_budget=4`, `localization_top_k=2`, `plan_samples_per_state=2`, and `max_realizations=4`; aggregate result was `12` real trajectories and `0` verified successes; `mini-rubocop` consistently edited files near the true region but still failed tests, while both codex runs remained stuck at `no_patch`; this sweep also exposed and fixed a runtime cleanup bug where `docker rm -f` timeout crashed an otherwise-finished sample command

## 2026-04-17T15:25:00Z swe-hippo-search-20260417
- purpose: rerun expanded real cascade search with Chutes student model `hippo-master/affine-17-5D7H7grKtvLJLy9GJWX8HEx2Z4swukjb9f8jAySR21UQEK9c` instead of `Qwen/Qwen3-32B-TEE`
- config: logs/real-tests/swe-hippo-search-20260417/README.txt
- runtime: local CPU + Docker
- status: completed-no-success
- cleanup: no remote rentals created; local artifacts retained under `logs/real-tests/swe-hippo-search-20260417/`
- notes: the model was callable via `chat/completions` even though it was not listed in Chutes `/models`; expanded `mini-rubocop` and `codex-rubocop` searches were run with `temps=0.2,0.5,0.8`, `localization_budget=6`, `localization_top_k=3`, `plan_samples_per_state=2`, and `max_realizations=6`; aggregate result was `12` real trajectories and `0` verified successes

## 2026-04-17T16:10:00Z swe-recipe-search-20260417
- purpose: rerun the real search using the exact requested recipe: 24 localization rollouts, keep 4, 2 plans per state, realize top 4 candidates, teacher rubric once, teacher repair cap 2
- config: logs/real-tests/swe-recipe-search-20260417/README.txt
- runtime: local CPU + Docker
- status: completed-no-success
- cleanup: no remote rentals created; local artifacts retained under `logs/real-tests/swe-recipe-search-20260417/`
- notes: both `mini-rubocop` and `codex-rubocop` were run on the real `rubocop__rubocop-7660` task with the requested Chutes student model; aggregate result was `8` real trajectories, `0` verified successes, and `0` near-miss branches, so the capped repair stage did not trigger

## 2026-04-17T18:05:00Z swe-python-recipe-20260417
- purpose: test the same fixed recipe on real Python SWE tasks to see whether the method shows any path toward a correct trajectory without changing the recipe
- config: logs/real-tests/swe-python-recipe-20260417/README.txt
- runtime: local CPU + Docker
- status: completed-no-success
- cleanup: no remote rentals created; local artifacts retained under `logs/real-tests/swe-python-recipe-20260417/`
- notes: `geopy__geopy-388` and `pre-commit__pre-commit-1299` were selected because their clean-workspace task tests pass, while `vega__altair-1958` was excluded after baseline failure; `mini-geopy` produced `4` trajectories and no near-miss, while `codex-geopy` produced `4` trajectories, `1` near-miss, `1` repair record, and `B/C` bucket samples but still `0` verified successes; both `pre-commit` recipe runs were blocked before rollout generation by teacher-endpoint instability (`503`, `504`, and a direct health-check read timeout)

## 2026-04-17T19:05:00Z swe-logic-fix-20260417
- purpose: diagnose whether the repeated zero-success SWE runs were caused by collector/runtime bugs rather than only by student-model weakness, then rerun the original failing command families and one downstream dependent command for each
- config: logs/real-tests/swe-logic-fix-20260417/README.txt
- runtime: local CPU + Docker
- status: completed-no-success
- cleanup: no remote rentals created; local artifacts retained under `logs/real-tests/swe-logic-fix-20260417/`
- notes: the diagnosis found two real collector issues: MiniSWE realization responses were often truncated before a closing bash fence and then discarded as `no_patch`, and some Codex responses emitted text-form `<tool_call>{...}</tool_call>` content that was ignored because no structured `tool_calls` field was present; after fixing those parsing/runtime issues and rerunning the original `mini-geopy` and `codex-rubocop` sample commands plus their downstream `relabel/build-buckets` commands, the collector moved from mostly fake `0-step no_patch` failures to mostly real executed trajectories with state files, changed files, and concrete syntax/test failures; verified success was still `0`, so remaining failures are now much more likely to reflect real student-model quality limits

## 2026-04-17T20:20:00Z swe-cleanup-and-fix-20260417
- purpose: restore the local Docker environment, add probe gating and rubric fallback to SWE collection, and rerun representative tasks end-to-end under the same recipe
- config: logs/real-tests/swe-cleanup-and-fix-20260417/README.txt
- runtime: local CPU + Docker
- status: completed-no-success
- cleanup: removed non-whitelist active Docker containers, pruned unused images, and preserved only `buildx_buildkit_*` plus `cluster-inst-*`; local artifacts retained under `logs/real-tests/swe-cleanup-and-fix-20260417/`
- notes: disk availability recovered from `2.7G` free at `100%` usage to `117G` free at `60%`; immediate external teacher health checks still showed `503`, but the collector now records probe status and can degrade rubric usage instead of aborting; first representative reruns (`mini-geopy`, `codex-rubocop`) validated the environment and manifest-count fixes but over-corrected into inspection-only `max_steps` failures, so a budget-aware realization nudge was added and the original sample commands were rerun again as `mini-geopy-v2` and `codex-rubocop-v2`; those v2 reruns produced real changed-file `verify_fail` trajectories, state files, downstream `relabel/build-buckets` outputs, and explicit collector-side `no_patch:truncated_action` labeling for the remaining format failure case

## 2026-04-17T21:55:00Z swe-realization-shift-20260417
- purpose: rerun the realization-heavy recipe after fixing host-side patch IO, full plan retention, escaped replacement decoding, and partial rubric/plan JSON fallback
- config: logs/real-tests/swe-realization-shift-20260417/README.txt
- runtime: local CPU + Docker
- status: completed-no-success
- cleanup: no remote rentals created; local artifacts retained under `logs/real-tests/swe-realization-shift-20260417/`
- notes: this rerun finally executed the intended shortlist honestly with `10` localization candidates, `6` patch plans, and `2` realized trajectories per task; `miniswe` improved materially on `rubocop__rubocop-7660` by producing `2/2` real target-file edits with repeated `Syntax OK` instead of the earlier escaped-newline syntax crash, but both trajectories still ended as `quality_fail + no_action` and downstream relabel produced `2` failure points with `0` repair records; `codex` on `rails__rails-38448` also benefited from non-empty rubric parsing, but both realized trajectories still died before any valid edit with `target_file does not exist` / `start_line must be >= 1`, so autonomous success remained `0` and both formats still emitted only `V` bucket rows

## 2026-04-17T23:15:00Z swe-success-prob-rerun-20260417
- purpose: implement existence-aware shortlist filtering, span-catalog realization, auto-verify after valid patch, cheap verify funnel, and wider near-miss / O-bucket gating, then rerun fixed-task real collection
- config: logs/real-tests/swe-success-prob-rerun-20260417/README.txt
- runtime: local CPU + Docker
- status: partial-improvement-no-success
- cleanup: no remote rentals created; local artifacts retained under `logs/real-tests/swe-success-prob-rerun-20260417/`
- notes: the first pass exposed a real runtime bug in `_copy_text_from_container()` which made `read_context()` and `build_span_catalog()` silently read empty files from task images; after fixing that bug, the original failing `codex-geopy sample` command plus downstream `relabel/build-buckets` were rerun and improved materially: `2/2` trajectories now produced real edits on `geopy/geocoders/here.py`, one reached `verify_fail` through the cheap verify stage, and the run emitted `B=2`, `C=2`, and `O=2`; `codex-rails` also improved relative to the older baseline by eliminating the previous `target_file does not exist` failure mode, but still stopped at `invalid_span`; `miniswe-rubocop` did not improve and remained blocked by `invalid_target` / no-action behavior under the stricter span-based schema

## 2026-04-17T23:59:00Z swe-teacher-online-judge-20260417
- purpose: validate the new online teacher-judge / branch-proposal collector path on fixed real SWE tasks and measure whether teacher-shaped branching changes the success funnel
- config: logs/real-tests/swe-teacher-online-judge-20260417/README.txt
- runtime: local CPU + Docker
- status: partial-improvement-no-success
- cleanup: no remote rentals created; local artifacts retained under `logs/real-tests/swe-teacher-online-judge-20260417/`
- notes: `miniswe/rubocop`, `codex/geopy`, and `codex/rails` all ran through real `sample -> relabel -> build-buckets`; no `A` or `T` success was sampled, but the online teacher changed the search funnel materially: `mini-rubocop` produced `3/3` changed-file trajectories with `2` real `verify_fail` rows and final `B=2 C=2 J=10 O=3 V=3`; `codex-geopy` still failed to realize robust patches but now produced non-empty `B/C/J/O`; `codex-rails` showed the clearest shift, with teacher online pulling the branch back to `activestorage/app/models/active_storage/variant.rb`, producing `3/3` changed-file trajectories, `3/3` syntax-pass rows, `2` real `verify_fail` rows, and final `B=2 C=2 J=16 O=3 V=3`

## 2026-04-18T00:40:00Z swe-checkpoint-tree-20260417
- purpose: replace the linear realization queue with checkpointed realization-tree search driven by teacher state summaries, then rerun fixed real tasks under the new search policy
- config: logs/real-tests/swe-checkpoint-tree-20260417/README.txt
- runtime: local CPU + Docker
- status: in-progress-partial-validation
- cleanup: no remote rentals created; local artifacts retained under `logs/real-tests/swe-checkpoint-tree-20260417/`
- notes: the code path is now live on real tasks and writes `search/checkpoints.jsonl`, `search/nodes.jsonl`, `search/teacher_state_summaries.jsonl`, and `states/`; real reruns uncovered three collector/runtime issues that were fixed immediately: (1) hard-coded `300s` OpenAI-compatible timeout caused multi-minute hangs, (2) eager root-node teacher summaries serialized teacher RTT across all shortlisted roots before any realization step, and (3) nested `{\"patch\": {...}}` student actions were being dropped as `no_action/parse_fail`; after each fix the original `mini-rubocop sample` command was rerun and targeted regression was rerun, but the full fixed-task `sample -> relabel -> build-buckets` closeout remains incomplete in this session because repeated localization/plan/summary requests are still inference-latency-bound

## 2026-04-18T09:10:00Z swe-hypothesis-tree-20260418
- purpose: validate the new root-race + repair-hypothesis tree search + multi-fidelity backup path on the same three fixed real SWE tasks and check whether it crosses the first `A`/`T` feasibility gate
- config: logs/real-tests/swe-hypothesis-tree-20260418/README.txt
- runtime: local CPU + Docker
- status: completed-no-success
- cleanup: no remote rentals created; local artifacts retained under `logs/real-tests/swe-hypothesis-tree-20260418/`
- notes: all three fixed tasks completed `sample -> relabel -> build-buckets`; the new path now writes `search/hypotheses.jsonl` in addition to checkpoints/nodes/teacher summaries, and run manifests record `root_nodes_total`, `root_race_rounds_run`, `hypothesis_nodes_total`, `hypothesis_children_total`, `teacher_hypotheses_total`, and `selection_tier_histogram`; the funnel improved on `mini-rubocop` and `codex-rails` in the sense that both produced real changed-file trajectories plus non-empty `B/C/J/O`, but no task produced `A` or `T` success, so the new strategy did not pass the original feasibility gate; `codex-geopy` regressed relative to the earlier success-prob rerun and produced only `J/V` plus failure points with zero changed-file trajectories

## 2026-04-18T11:20:00Z swe-upstream-blackbox-targon-20260418a
- purpose: validate the new ORBIT black-box wrapper against upstream `affinetes` `SWE-INFINITE` on a fresh isolated Targon rental using real `codex` and `miniswe` evaluate runs
- config: logs/real-tests/swe-blackbox-targon-20260418/README.txt
- workload: swe-upstream-blackbox-20260418a
- machine: swe-upstream-blackbox-20260418a
- status: succeeded-cleaned
- cleanup: `wrk-aqfeqmbiuxxi` and `wrk-ucjqnk3icdei` terminated after artifact capture; active RENTAL list rechecked empty
- notes: target upstream ref `374f2034edcbb2cc6d5c93142759070a2578c39c`; first launch attempt failed with `TARGON_PROJECT_ID not set`; recovery created project `prj-0f96o65vhukw` and SSH key `shk-sdnwzg2ghpye`; `cpu-small` inventory was used; the first recovered rental on `wangtong123/orbit:latest` stayed in `provisioning` and was deleted; the second recovered rental on `ghcr.io/manifold-inc/ubuntu-systemd-docker:v1` reached SSH-ready state and completed real remote `codex` plus `miniswe` black-box runs; remote `codex` matched the local failure family (`Failed to install Codex CLI in container`), and remote `miniswe` matched the local timeout behavior after switching from the invalid `OPENAI_API_KEY` path to the valid `CHUTES_API_KEY` path

## 2026-04-18T13:35:00Z swe-openenv-checkpoint-targon-20260418a
- purpose: validate upstream `SWE-INFINITE` OpenEnv `checkpoint/restore` on a fresh isolated Targon CPU rental through the ORBIT black-box wrapper
- config: logs/real-tests/swe-openenv-checkpoint-targon-20260418/README.txt
- workload: swe-oenv-ckpt-0418a
- machine: swe-oenv-ckpt-0418a
- host: 72.46.85.157:30562
- status: succeeded-cleaned
- cleanup: `wrk-pnhjciw3rfj3` terminated after artifact capture; final active RENTAL list empty
- notes: first remote reset attempt failed because Docker daemon was not running inside `ghcr.io/manifold-inc/ubuntu-systemd-docker:v1`; after starting `dockerd` manually and rerunning the original `openenv reset` command plus the downstream full roundtrip script, the remote wrapper produced `checkpoint0`, `checkpoint1`, `probe1=FILE_PRESENT`, `probe0=FILE_MISSING`, and `stop.out` with `stopped=true`

## 2026-04-18T13:45:00Z swe-openenv-checkpoint-targon-20260418b
- purpose: rerun the upstream `SWE-INFINITE` OpenEnv `checkpoint/restore` rental validation with automatic Docker-daemon bootstrap in the remote validation script
- config: logs/real-tests/swe-openenv-checkpoint-targon-20260418/README.txt
- workload: swe-oenv-ckpt-0418b
- machine: swe-oenv-ckpt-0418b
- host: 72.46.85.157:30838
- status: succeeded-cleaned
- cleanup: `wrk-6kibels2fw00` terminated after artifact capture; final active RENTAL list empty
- notes: the updated remote script started `dockerd` automatically when `docker version` failed; the rerun then completed the full `reset -> checkpoint -> step -> state -> checkpoint -> step -> restore -> step -> restore -> step -> stop` sequence without manual intervention and produced `probe1=FILE_PRESENT` plus `probe0=FILE_MISSING`

## 2026-04-18T14:05:00Z swe-openenv-checkpoint-targon-20260418c
- purpose: rerun the remote OpenEnv checkpoint/restore validation after making the `remote` CLI family lazy so unrelated `data` commands no longer warn when `httpx` is absent
- config: logs/real-tests/swe-openenv-checkpoint-targon-20260418/README.txt
- workload: swe-oenv-ckpt-0418c
- machine: swe-oenv-ckpt-0418c
- host: 72.46.85.157:31692
- status: succeeded-cleaned
- cleanup: `wrk-egzql4l2mphq` terminated after artifact capture; final active RENTAL list empty
- notes: the lazy-loading change in `orbit.remote_ops.cli` removed the spurious `Warning: failed to load CLI command 'remote': No module named 'httpx'` line from remote `orbit data ...` invocations; the remote roundtrip still completed successfully with `probe1=FILE_PRESENT` and `probe0=FILE_MISSING`

## 2026-04-18T14:20:00Z swe-openenv-synth-targon-20260418a
- purpose: validate real SWE synthesis on top of upstream OpenEnv using a single teacher model for action generation, with checkpoint/save, retry, and restore recorded in raw events
- config: logs/real-tests/swe-openenv-synthesis-targon-20260418/README.txt
- workload: swe-oenv-synth-0418a
- machine: swe-oenv-synth-0418a
- host: 72.46.85.157:31176
- status: succeeded-cleaned
- cleanup: `DELETE /tha/v2/workloads/wrk-7j77v0xopqys`; final active RENTAL list empty
- notes: the first remote run on upstream ref `7e1f48ec380a2e254d72c9cf6cc1e9cda0f8cc7e` only produced a generic listing because the reset observation was still incomplete; after switching the affinetes fork ref to `9154d06c8bdef7d3f7fabb0d7e17848cf7799c35`, subsequent reruns produced full task observations, targeted `git grep`, file views on `lib/rubocop/cop/style/block_delimiters.rb`, repeated baseline restore / retry behavior, and multiple direct edit attempts (`python`, `perl -0pi -e`, `ruby -0pi -e`, `ruby - <<'RUBY'`); the captured states in `remote-rerun-c/d/e` still reported `changed_files: (none)`, but the OpenEnv save-state / retry / rollback mechanics were exercised in real remote synthesis runs

## 2026-04-18T15:25:00Z swe-openenv-synth-targon-20260418b
- purpose: validate OpenEnv synthesis with separate student and teacher models, using `gpt-5.4-medium` for trajectory generation and `gpt-5.4` for teacher fallback on a fresh isolated Targon CPU rental
- config: logs/real-tests/swe-openenv-synthesis-targon-20260418/README.txt
- workload: swe-oenv-synth-0418b
- machine: swe-oenv-synth-0418b
- status: failed-cleaned
- cleanup: `DELETE /tha/v2/workloads/wrk-fvaj7d9tafsu`
- notes: local and remote minimal probes both returned `503 model_not_found` for `gpt-5.4-medium` and HTTP success for `gpt-5.4`; the original remote `synthesize` command for the requested `gpt-5.4-medium + gpt-5.4` pair was rerun multiple times after fixing remote script entrypoint, remote package sync, `openai` dependency installation, upstream fork `.git` sync, and `safe.directory`; the final gating blocker for the requested student model remained endpoint-side model availability

## 2026-04-18T15:50:00Z swe-openenv-synth-targon-20260418c
- purpose: validate the same OpenEnv synthesis environment on a fresh isolated Targon CPU rental using `gpt-5.4` as both trajectory model and teacher fallback after the `gpt-5.4-medium` endpoint blocker
- config: logs/real-tests/swe-openenv-synthesis-targon-20260418/README.txt
- workload: swe-oenv-synth-0418c
- machine: swe-oenv-synth-0418c
- host: 72.46.85.157:32659
- status: succeeded-cleaned
- cleanup: `DELETE /tha/v2/workloads/wrk-y7lyc3abztel`; final active RENTAL list empty
- notes: this run installed `orbit[control]`, synced `pyproject.toml` and the affinetes fork with `.git`, copied the runtime key file, and then executed four remote synthesis reruns plus one manual OpenEnv probe attempt; `g` completed after the `responses.create` parser fix with `student_calls=1`, `teacher_calls=7`, and final observation `needle not found or ambiguous`; `h` completed with `student_calls=1`, `teacher_calls=0`, and a non-zero empty observation; `i` completed twice with `model=gpt-5.4`, `teacher_model=gpt-5.4`, and `reasoning_effort=teacher_reasoning_effort=medium`, recording `latest_changed_files=[]` in both runs; `j` was started with `max_root_retries=1` and `max_edit_retries=1` and wrote `reset/checkpoint/model_action` events before rental cleanup; manual probe `k` first failed because `openenv reset` does not accept `--api-key-file`, and the rerun failed with `openenv server did not become ready`

## 2026-04-18T16:40:00Z swe-openenv-synth-targon-20260418d
- purpose: continue the Targon CPU OpenEnv synthesis validation after fixing the wrapper and upstream environment, and verify that a codex task environment reports real `changed_files` and restore behavior under checkpointed control
- config: logs/real-tests/swe-openenv-synthesis-targon-20260418/README.txt
- workload: swe-oenv-synth-0418d
- machine: swe-oenv-synth-0418d
- host: 72.46.85.157:30487
- status: succeeded-cleaned
- cleanup: `DELETE /tha/v2/workloads/wrk-r8gwpyhmz3m8`; final active RENTAL list empty
- notes: this run fixed the active environment path in two places: ORBIT `openenv reset` accepted `--api-key-file` and switched the OpenEnv server socket to a short `/tmp` path, and the affinetes fork advanced to `2f90b9c957af5b581937cc6835dda4e7be5e64fa` where `SWE-INFINITE.step()` refreshes `last_patch_hash` and `last_changed_files`; manual probe `k` then recorded `changed_files: lib/rubocop/cop/style/block_delimiters.rb` after a one-line source edit and `changed_files: (none)` after restore; downstream synth rerun `l` completed with `model=gpt-5.4`, `teacher_model=gpt-5.4`, `reasoning_effort=teacher_reasoning_effort=medium`, `edit_checkpoint_id=1691b7cfb8284fa3bd6892b2608007bc-ckpt-2`, and `latest_changed_files=["config/default.yml"]`

## 2026-04-18T17:10:00Z swe-openenv-synth-targon-20260418e
- purpose: continue the Targon CPU OpenEnv synthesis validation on Go and Python tasks using `gpt-5.4` as both trajectory model and teacher fallback, and record whether the codex task environment produces real `changed_files`
- config: logs/real-tests/swe-openenv-synthesis-targon-20260418/README.txt
- workload: swe-oenv-synth-0418e
- machine: swe-oenv-synth-0418e
- host: 72.46.85.157:31180
- status: succeeded-cleaned
- cleanup: `DELETE /tha/v2/workloads/wrk-ruy6ukeuegx5`; final active RENTAL list empty
- notes: this run used affinetes ref `2f90b9c957af5b581937cc6835dda4e7be5e64fa` on a fresh `cpu-small` rental with the same DIND image; Go task `2` / `ajvb__kala-202` completed synth rerun `m` with `student_calls=2`, `teacher_calls=6`, `edit_checkpoint_id=b3ff6424081f4fd9ba1006e44976cbe5-ckpt-2`, and `latest_changed_files=["main.go"]`; Python task `19` / `demisto__content-5504` completed synth rerun `n` with `student_calls=3`, `teacher_calls=5`, `edit_checkpoint_id=6894e92dea704ccb9fb406222b89a873-ckpt-2`, `latest_changed_files=["release_notes.py"]`, and final observation `verified`; local artifact sync captured both remote run directories under `logs/real-tests/swe-openenv-synthesis-targon-20260418/artifacts/`

## 2026-04-18T18:40:00Z swe-openenv-synth-targon-20260418f
- purpose: compare no-retry vs retry-enabled end-to-end OpenEnv synthesis on Go and Python tasks using `gpt-5.4` as both trajectory model and teacher fallback, and record whether `restore` events appear and whether final patch quality changes
- config: logs/real-tests/swe-openenv-synthesis-targon-20260418/README.txt
- workload: swe-oenv-synth-0418f
- machine: swe-oenv-synth-0418f
- host: 72.46.85.157:30491
- status: succeeded-cleaned
- cleanup: `DELETE /tha/v2/workloads/wrk-ob9v160hglqh`; final active RENTAL list empty
- notes: the controller changes exercised on this rental included upstream submit-command materialization, edited-state stall detection, glob-safe viewed-file extraction, and prompt recovery for `ruby: command not found` plus `ImportError: No module named pathlib`; the retained no-retry Python run `remote-rerun-y2_py_noretry` recorded `student_calls=2`, `teacher_calls=6`, `root_retries_used=0`, `edit_retries_used=0`, `latest_changed_files=["release_notes.py"]`, and no restore events; the retained retry-enabled Python run `remote-rerun-z2_py_retry` recorded a real `restore` event with `scope: edit` for checkpoint `c0595b29a48841b29889188e560decbb-ckpt-2` after the same `release_notes.py` patch state, and the post-restore action switched to a different `python3` edit path; the clean Go comparison was not retained as a separate finalized run in this campaign directory, while earlier Go evidence remains under `remote-rerun-m-go`

## 2026-04-18T18:45:27Z swe-h200-sglang-student-20260418
- purpose: run a fresh isolated `h200-small` rental, serve `axon1/affine_m28_5Ci7FgT3HB5rYKuaG6aKTfYyaXAgjaJyHLadMNgXENzmcgLh` through SGLang as the student model, keep teacher guidance on `gpt-5.4`, and validate end-to-end codex-style synthesis on one Go task and one Python task
- config: logs/real-tests/swe-h200-sglang-student-20260418/README.txt
- workload: wrk-g94qk5jts0lk
- machine: swe-h200-sglang-0418a
- host: 72.46.85.157:30166
- status: running-followup
- cleanup: H200 student rental `wrk-g94qk5jts0lk` and CPU collector rental `wrk-zlg6oiyxvp71` intentionally retained for active follow-up
- notes: affinetes ref `2f90b9c957af5b581937cc6835dda4e7be5e64fa`; H200 student service is up on `swe-h200-sglang-0418a`; CPU collector `swe-cpu-collector-0418a` reaches the student through an SSH tunnel at `http://127.0.0.1:30001/v1`; the controller now falls back from `responses.create(...)` to `chat.completions.create(...)` for the student endpoint; CPU-side Python task `19` produced a completed collected run `cpu-py-b` with `student_calls=8`, `teacher_calls=0`, `latest_changed_files=[]`, and repeated `git log --oneline` actions; subsequent follow-up reruns continue on Targon only with updated no-progress and teacher-fallback logic
## 2026-04-18T20:55:00Z swe-h200-sglang-batch10-20260418
- purpose: run 10 parallel Targon-only SWE synth jobs on the active H200 student plus CPU collector pair and record whether larger sampling yields changed files or verified outcomes
- config: logs/real-tests/swe-h200-sglang-batch10-20260418/README.txt
- workload: wrk-g94qk5jts0lk, wrk-zlg6oiyxvp71
- machine: swe-h200-sglang-0418a, swe-cpu-collector-0418a
- host: 72.46.85.157:30166, 72.46.85.157:32315
- status: running
- cleanup: current turn
- notes: batch uses 5 Python task 19 runs and 5 Go task 2 runs through the collector-host tunnel at `http://127.0.0.1:30001/v1`; launcher PID on collector is `11765`

## 2026-04-18T21:20:00Z swe-h200-sglang-batch10-fix1-20260418
- purpose: rerun the 10-way distributed synth batch after removing the hard-coded ruby edit bias and preferring python3-based edit actions
- config: logs/real-tests/swe-h200-sglang-batch10-fix1-20260418/README.txt
- workload: wrk-g94qk5jts0lk, wrk-zlg6oiyxvp71, wrk-2hcbupk8w8h9, wrk-h032t8zr1jsw, wrk-tfktfuq8xdid, wrk-y4r0535ocuds
- machine: swe-h200-sglang-0418a, swe-cpu-collector-0418a, swe-cpu-collector-0418b, swe-cpu-collector-0418c, swe-cpu-collector-0418d, swe-cpu-collector-0418e
- host: 72.46.85.157:30166, 72.46.85.157:32315, 72.46.85.157:32293, 72.46.85.157:31117, 72.46.85.157:32025, 72.46.85.157:32148
- status: planned
- cleanup: current turn
- notes: fix1 syncs updated `orbit/integrations/affinetes_swe/synthesis.py` to all five collectors before relaunch

## 2026-04-19T10:05:00Z swe-qwen36-promptmatch-batch10-20260419
- purpose: run a larger end-to-end SWE synth batch after changing student prompting to match upstream `affinetes` message templates and limiting teacher intervention to branch selection plus hidden think injection
- config: logs/real-tests/swe-qwen36-promptmatch-batch10-20260419/README.txt
- workload: wrk-g94qk5jts0lk, wrk-zlg6oiyxvp71, wrk-2hcbupk8w8h9, wrk-h032t8zr1jsw, wrk-tfktfuq8xdid, wrk-y4r0535ocuds
- machine: swe-h200-sglang-0418a, swe-cpu-collector-0418a, swe-cpu-collector-0418b, swe-cpu-collector-0418c, swe-cpu-collector-0418d, swe-cpu-collector-0418e
- host: 72.46.85.157:30166, 72.46.85.157:32315, 72.46.85.157:32293, 72.46.85.157:31117, 72.46.85.157:32025, 72.46.85.157:32148
- status: running-followup
- cleanup: current turn
- notes: batch uses `Qwen/Qwen3.6-35B-A3B` on the H200 student service through existing SSH tunnels from five CPU collectors; initial launch needed two fixes (`v2` did not export child env vars, and collectors `b-e` needed `AFF_ROOT=/root/affinetes-fork-batch`); current evidence shows all inspected runs use upstream-shaped first prompts (`system + user(instance)`), no run emits `model_action(actor=teacher)`, Go runs `a/b/d` emit `teacher_branch=1`, no run emits `teacher_think`, and current manifests (`a-go`, `b-go`, `c-go`, `d-go`, `e-go`, `a-py`) all still have `latest_changed_files=[]`

## 2026-04-19T11:15:00Z swe-qwen36-structured-batch20-20260419
- purpose: run a larger structured-controller SWE synth batch after switching controller judgment to teacher-provided structured JSON decisions with full privileged context and history
- config: logs/real-tests/swe-qwen36-structured-batch20-20260419/README.txt
- workload: wrk-g94qk5jts0lk, wrk-zlg6oiyxvp71, wrk-2hcbupk8w8h9, wrk-h032t8zr1jsw, wrk-tfktfuq8xdid, wrk-y4r0535ocuds
- machine: swe-h200-sglang-0418a, swe-cpu-collector-0418a, swe-cpu-collector-0418b, swe-cpu-collector-0418c, swe-cpu-collector-0418d, swe-cpu-collector-0418e
- host: 72.46.85.157:30166, 72.46.85.157:32315, 72.46.85.157:32293, 72.46.85.157:31117, 72.46.85.157:32025, 72.46.85.157:32148
- status: running-followup
- cleanup: current turn
- notes: this batch reuses the existing H200 student and five collector rentals, syncs the new `teacher_decision`-based controller to each collector, and runs 20 samples total (`py-19a/b`, `go-2a/b` on each collector) with higher retry budgets to measure whether structured teacher intervention yields more `teacher_think`, more `changed_files`, or any correct samples; current evidence from all five collectors shows upstream-shaped student prompts, repeated `teacher_decision + teacher_think` on Go runs, initial `teacher_decision + teacher_think` on Python runs, no `model_action(actor=teacher)`, no `teacher_branch` yet, and still `changed_files=0` / `verified=0`; follow-up remote format check on collector `a` confirms teacher-think is now merged into the existing final `user` turn (`system,user` roles preserved, `<teacher_guidance>` embedded inside the last user message) rather than appended as an extra user turn; fresh unpatched teacher calls are currently blocked by `401 invalid_api_key` on collector `a`

## 2026-04-19T12:55:00Z swe-qwen36-longrun-batch10-20260419
- purpose: run a steadier long-run batch after fixing teacher endpoint resolution and teacher-think merge format, to check whether corrected teacher intervention can now reach `changed_files` or `verified` samples
- config: logs/real-tests/swe-qwen36-longrun-batch10-20260419/README.txt
- workload: wrk-g94qk5jts0lk, wrk-zlg6oiyxvp71, wrk-2hcbupk8w8h9, wrk-h032t8zr1jsw, wrk-tfktfuq8xdid, wrk-y4r0535ocuds
- machine: swe-h200-sglang-0418a, swe-cpu-collector-0418a, swe-cpu-collector-0418b, swe-cpu-collector-0418c, swe-cpu-collector-0418d, swe-cpu-collector-0418e
- host: 72.46.85.157:30166, 72.46.85.157:32315, 72.46.85.157:32293, 72.46.85.157:31117, 72.46.85.157:32025, 72.46.85.157:32148
- status: running-followup
- cleanup: current turn
- notes: batch keeps concurrency at 10 total runs (`py-19`, `go-2` on each collector) to reduce H200 saturation; teacher endpoint is explicitly pinned to `https://api.aicodemirror.com/api/codex/backend-api/codex/v1`, and the active controller now resolves the same endpoint automatically when a teacher key is provided without an explicit teacher base; relaunch needed one script fix because the first generated remote launchers referenced an unexpanded `BASE` variable and exited immediately; after relaunch, all inspected Go runs now emit `teacher_decision + teacher_think + model_action + step + state`, proving the teacher authentication/base-url blocker is cleared, but no run has reached `changed_files` or `verified` yet

## 2026-04-19T12:58:00Z swe-fakemoon-sglang-20260419
- purpose: switch the student model to `fakemoonlo/Affine-5FnfLT3ntQXDsAnVC5H5WNQYVTY7SSCbxU3kxqhNybtJeNGb` under `sglang` and re-check whether the current structured-controller strategy yields valid early SWE synth trajectories
- config: logs/real-tests/swe-fakemoon-sglang-20260419/README.txt
- workload: wrk-g94qk5jts0lk, wrk-zlg6oiyxvp71, wrk-2hcbupk8w8h9, wrk-h032t8zr1jsw, wrk-tfktfuq8xdid, wrk-y4r0535ocuds
- machine: swe-h200-sglang-0418a, swe-cpu-collector-0418a, swe-cpu-collector-0418b, swe-cpu-collector-0418c, swe-cpu-collector-0418d, swe-cpu-collector-0418e
- host: 72.46.85.157:30166, 72.46.85.157:32315, 72.46.85.157:32293, 72.46.85.157:31117, 72.46.85.157:32025, 72.46.85.157:32148
- status: running-followup
- cleanup: current turn
- notes: existing `Qwen/Qwen3.6-35B-A3B` collector runs were stopped before the model switch; H200 service was restarted as `sglang.launch_server --model-path fakemoonlo/Affine-5FnfLT3ntQXDsAnVC5H5WNQYVTY7SSCbxU3kxqhNybtJeNGb --tool-call-parser qwen25 --reasoning-parser qwen3`; the model publishes `/v1/models` successfully under `sglang`; raw `sglang /generate` succeeds and emits `<think>...</think>` text; ORBIT was then patched to add a native `sglang /generate` fallback using a rendered chat-template prompt from `transformers.AutoTokenizer.apply_chat_template(...)`; after installing `transformers` on collector `a`, minimal `go-2` synth completed end-to-end with `student_calls=3`, `teacher_calls=3`, `teacher_think_calls=3`, `latest_changed_files=[\"main.go\"]`, and `final_done=true`; this proves the pipeline can now collect a full sample with the fakemoon model, though the resulting patch is still incorrect

## 2026-04-19T13:18:00Z swe-fakemoon-no-teacher-batch10-20260419
- purpose: run 10 no-teacher fakemoon rollouts to see whether the model can produce any correct SWE samples without teacher intervention
- config: logs/real-tests/swe-fakemoon-no-teacher-batch10-20260419/README.txt
- workload: wrk-g94qk5jts0lk, wrk-zlg6oiyxvp71, wrk-2hcbupk8w8h9, wrk-h032t8zr1jsw, wrk-tfktfuq8xdid, wrk-y4r0535ocuds
- machine: swe-h200-sglang-0418a, swe-cpu-collector-0418a, swe-cpu-collector-0418b, swe-cpu-collector-0418c, swe-cpu-collector-0418d, swe-cpu-collector-0418e
- host: 72.46.85.157:30166, 72.46.85.157:32315, 72.46.85.157:32293, 72.46.85.157:31117, 72.46.85.157:32025, 72.46.85.157:32148
- status: running-followup
- cleanup: current turn
- notes: batch runs without `teacher_model`, without `inject_teacher_think`, and with `max_root_retries=0`, `max_edit_retries=0`; rollout transport uses the new `sglang /generate` fallback for the student model; after wave 1 and a higher-temperature wave 2, no correct sample has been observed, no inspected rollout has reached `changed_files`, and the dominant no-teacher pattern is conservative exploration (`ls -la`, `find *.go`, `cat main.go`) rather than real edits

## 2026-04-19T14:45:00Z swe-fakemoon-eval-batch10-20260419
- purpose: rerun fakemoon student evaluation in true eval mode with no teacher intervention, stopping on `32k` rendered context, model stop, or upstream OpenEnv termination rather than a small fixed step budget
- config: logs/real-tests/swe-fakemoon-eval-batch10-20260419/README.txt
- workload: wrk-g94qk5jts0lk, wrk-zlg6oiyxvp71, wrk-2hcbupk8w8h9, wrk-h032t8zr1jsw, wrk-tfktfuq8xdid, wrk-y4r0535ocuds
- machine: swe-h200-sglang-0418a, swe-cpu-collector-0418a, swe-cpu-collector-0418b, swe-cpu-collector-0418c, swe-cpu-collector-0418d, swe-cpu-collector-0418e
- host: 72.46.85.157:30166, 72.46.85.157:32315, 72.46.85.157:32293, 72.46.85.157:31117, 72.46.85.157:32025, 72.46.85.157:32148
- status: running
- cleanup: current turn
- notes: synced updated `orbit/integrations/affinetes_swe/synthesis.py` and `orbit/cli_data.py` to all five collectors, then launched 10 distinct tasks (`1..10`) with `--eval-mode --eval-max-context-tokens 32768 --student-enable-thinking --step-limit 200 --max-steps 200`; existing verified SSH tunnels on each collector continue to expose the H200 student as `http://127.0.0.1:30001/v1`; first health check shows all launcher PIDs present and at least 6 of the 10 runs already writing `raw/synthesis_events.jsonl`

## 2026-04-19T18:10:00Z swe-fakemoon-eval-batch10-fix1-20260419
- purpose: rerun the same 10-task fakemoon eval batch after removing eval-mode command mutation and raising the native `sglang /generate` completion budget to `4096`
- config: logs/real-tests/swe-fakemoon-eval-batch10-fix1-20260419/README.txt
- workload: wrk-g94qk5jts0lk, wrk-zlg6oiyxvp71, wrk-2hcbupk8w8h9, wrk-h032t8zr1jsw, wrk-tfktfuq8xdid, wrk-y4r0535ocuds
- machine: swe-h200-sglang-0418a, swe-cpu-collector-0418a, swe-cpu-collector-0418b, swe-cpu-collector-0418c, swe-cpu-collector-0418d, swe-cpu-collector-0418e
- host: 72.46.85.157:30166, 72.46.85.157:32315, 72.46.85.157:32293, 72.46.85.157:31117, 72.46.85.157:32025, 72.46.85.157:32148
- status: running-followup
- cleanup: current turn
- notes: synced updated `synthesis.py` and `cli_data.py` to all five collectors; launched tasks `1..10` with `--student-max-new-tokens 4096`; first launch hit transient upstream baseline-checkpoint failures on `b/task-3` and `d/task-7` (`No such container` during snapshot), both were cleared and relaunched; current observed behavior is much lower throughput than the previous `1024`-token batch, with most runs still only reaching `step_index 0` or `1`, so fix effectiveness on `generation_truncated` has not yet been measured

## 2026-04-19T18:17:00Z swe-qwen36-eval-batch10-20260419
- purpose: switch the active H200 student from fakemoon to `Qwen/Qwen3.6-35B-A3B`, keep `sglang`, raise static memory fraction to `0.95`, and relaunch the same 10-task no-teacher eval batch
- config: logs/real-tests/swe-qwen36-eval-batch10-20260419/README.txt
- workload: wrk-g94qk5jts0lk, wrk-zlg6oiyxvp71, wrk-2hcbupk8w8h9, wrk-h032t8zr1jsw, wrk-tfktfuq8xdid, wrk-y4r0535ocuds
- machine: swe-h200-sglang-0418a, swe-cpu-collector-0418a, swe-cpu-collector-0418b, swe-cpu-collector-0418c, swe-cpu-collector-0418d, swe-cpu-collector-0418e
- host: 72.46.85.157:30166, 72.46.85.157:32315, 72.46.85.157:32293, 72.46.85.157:31117, 72.46.85.157:32025, 72.46.85.157:32148
- status: running
- cleanup: current turn
- notes: H200 service now runs `python3 -m sglang.launch_server --model-path Qwen/Qwen3.6-35B-A3B --tool-call-parser qwen --reasoning-parser qwen3 --mem-fraction-static 0.95`; before relaunching eval, the H200 runtime needed `sglang==0.5.10.post1` plus `nvidia-cuda-toolkit` so JIT kernels could find `nvcc`; `/v1/models` and `/v1/chat/completions` both validate after the repair; collector drift was discovered during the first relaunch attempt (`a` lacked `--eval-mode`, others still ran an older `synthesis.py` that required a student key), so `orbit/cli_data.py` and `orbit/integrations/affinetes_swe/synthesis.py` were re-synced to all five collectors before the final launch; the final 10-task relaunch uses per-task `run.sh` wrappers with `nohup`, includes `--api-key dummy`, and currently has all ten task processes alive while `raw/synthesis_events.jsonl` is still at size `0` during the earliest initialization window

## 2026-04-19T20:18:00Z swe-qwen35fp8-eval-batch10-cg-radix-20260419
- purpose: switch the active H200 student to `Qwen/Qwen3.5-27B-FP8`, keep `sglang`, enable CUDA graph and radix cache, and rerun the same 10-task no-teacher eval batch
- config: logs/real-tests/swe-qwen35fp8-eval-batch10-cg-radix-20260419/README.txt
- workload: wrk-g94qk5jts0lk, wrk-zlg6oiyxvp71, wrk-2hcbupk8w8h9, wrk-h032t8zr1jsw, wrk-tfktfuq8xdid, wrk-y4r0535ocuds
- machine: swe-h200-sglang-0418a, swe-cpu-collector-0418a, swe-cpu-collector-0418b, swe-cpu-collector-0418c, swe-cpu-collector-0418d, swe-cpu-collector-0418e
- host: 72.46.85.157:30166, 72.46.85.157:32315, 72.46.85.157:32293, 72.46.85.157:31117, 72.46.85.157:32025, 72.46.85.157:32148
- status: running
- cleanup: current turn
- notes: H200 service now runs `python3 -m sglang.launch_server --model-path Qwen/Qwen3.5-27B-FP8 --tool-call-parser qwen --reasoning-parser qwen3 --fp8-gemm-backend flashinfer_deepgemm --mem-fraction-static 0.95` with CUDA graph and radix cache enabled; enabling this path required upgrading `flashinfer-python` and `flashinfer-cubin` to `0.6.8.post1`, installing `libcublas-dev-12-8`, and exporting `CPLUS_INCLUDE_PATH=/usr/local/cuda/include` so FlashInfer JIT uses CUDA 12.8 headers; a local 10-concurrency short-request probe improved from about `92.8 - 96.4 tok/s` to `762.09 tok/s`; collectors were re-synced to the current `cli_data.py` and `synthesis.py` before launch, and the batch uses `/root/orbit-batch`, `/root/affinetes-fork-batch`, and the existing local tunnel `http://127.0.0.1:30001/v1`

## 2026-04-19T20:50:00Z swe-qwen35fp8-teacher-batch20-codex-20260419
- purpose: start a larger teacher-assisted SWE synthesis batch once `Qwen/Qwen3.5-27B-FP8` trajectory collection was verified on the current `sglang + flashinfer_deepgemm` serving path
- config: logs/real-tests/swe-qwen35fp8-teacher-batch20-codex-20260419/README.txt
- workload: wrk-g94qk5jts0lk, wrk-zlg6oiyxvp71, wrk-2hcbupk8w8h9, wrk-h032t8zr1jsw, wrk-tfktfuq8xdid, wrk-y4r0535ocuds
- machine: swe-h200-sglang-0418a, swe-cpu-collector-0418a, swe-cpu-collector-0418b, swe-cpu-collector-0418c, swe-cpu-collector-0418d, swe-cpu-collector-0418e
- host: 72.46.85.157:30166, 72.46.85.157:32315, 72.46.85.157:32293, 72.46.85.157:31117, 72.46.85.157:32025, 72.46.85.157:32148
- status: running
- cleanup: current turn
- notes: teacher uses `gpt-5.4` via the Codex-compatible proxy `https://api.aicodemirror.com/api/codex/backend-api/codex/v1` with `/root/orbit-batch/.runtime_teacher_key` on each collector; student remains `Qwen/Qwen3.5-27B-FP8` served by `sglang` with CUDA graph and radix cache enabled; batch size is 20 tasks split across the 5 existing dedicated collectors

## 2026-04-20T05:40:00Z swe-qwen35fp8-teacher-qwen36fp8-centralized-20260420
- purpose: repair local-Qwen student no-content failures, migrate from five distributed `cpu-small` collectors to one isolated `cpu-large`, and validate the new centralized teacher-assisted SWE collection path
- config: logs/real-tests/swe-qwen35fp8-teacher-qwen36fp8-centralized-20260420/README.txt
- workload: wrk-g94qk5jts0lk, wrk-lfec9bp041p4, wrk-cjrs8a2n9y9j
- machine: swe-h200-sglang-0418a, swe-h200-teacher-qwen36fp8-0420a, swe-cpu-large-central-0420a
- host: 72.46.85.157:30166, 72.46.85.157:31490, 72.46.85.157:32422
- status: running-followup
- cleanup: five old `cpu-small` collectors terminated after centralized smoke passed; new centralized collector kept alive for follow-up
- notes: centralized collector now tunnels student at `127.0.0.1:30001/v1` and teacher at `127.0.0.1:30002/v1`; a synchronous centralized smoke on `task-15` completed through `teacher_decision -> teacher_think -> model_action -> step -> state` with `student_calls=2` and `teacher_calls=2`; local-Qwen student no-content retry is now implemented and tested, but the full `1..20` restart remains blocked because `/tmp/swe-infinite-cache/task_00000000012.json` is absent on all prior machines and direct public R2 fetch returns `404`

## 2026-04-20T07:53:16Z swe-qwen35fp8-teacher-qwen36fp8-fresh10-fix1-20260420
- purpose: cap student context at `65536`, add rolling edit checkpoints plus deterministic anti-loop rollback escalation, fetch a fresh 10-task batch from public R2, and relaunch centralized teacher-assisted collection on tasks not previously attempted
- config: logs/real-tests/swe-qwen35fp8-teacher-qwen36fp8-fresh10-fix1-20260420/README.txt
- workload: wrk-g94qk5jts0lk, wrk-lfec9bp041p4, wrk-cjrs8a2n9y9j
- machine: swe-h200-sglang-0418a, swe-h200-teacher-qwen36fp8-0420a, swe-cpu-large-central-0420a
- host: 72.46.85.157:30166, 72.46.85.157:31490, 72.46.85.157:32422
- status: running
- cleanup: current turn
- notes: student H200 was restarted with `--context-length 65536`; fresh task selection was staged from public R2 into `/tmp/swe-infinite-cache` and persisted as `selected_tasks.json`; the first fresh launch failed fast because the old synth path still requires `--api-key dummy`, and the second launch using the old hardcoded upstream ref failed because GitHub no longer serves `8ceca1f6ccff6ec8c76e676c3473a9f8fc594e87`; the active `fix1` relaunch now uses `--upstream-repo-path /root/affinetes-fork --upstream-ref 2f90b9c957af5b581937cc6835dda4e7be5e64fa`, plus `--api-key dummy --teacher-api-key dummy`, and has already shown real early rollout signals: `task-35` reached `reset -> checkpoint -> teacher_decision -> teacher_think`, while `task-38` reached `reset -> checkpoint -> teacher_decision -> model_action -> step -> state`

## 2026-04-20T17:24:00Z swe-qwen36-clean-eval-batch100-fastfix-smoke10-20260420
- purpose: validate the bounded launcher, shared runtime cache, explicit ready gate, and clean-eval transport retry on the first 10 tasks of the existing qwen36 batch100 selection before relaunching the full 100-task run
- config: logs/real-tests/swe-qwen36-clean-eval-batch100-fastfix-smoke10-20260420/README.txt
- workload: wrk-g94qk5jts0lk, wrk-cjrs8a2n9y9j
- machine: swe-h200-sglang-0418a, swe-cpu-large-central-0420a
- host: 72.46.85.157:30166, 72.46.85.157:32422
- status: running-followup
- cleanup: smoke launcher was terminated after validation; same collector and H200 kept alive for the follow-up full batch
- notes: fixed two ready-gate bugs before the smoke could start cleanly: local qwen smoke `chat.completions` may return `reasoning_content` with `content=null`, and the H200 ready marker must be checked with remote `grep` instead of remote `tail`; after those fixes the smoke landed `ready_gate.json`, reached `9/10` started tasks with `0` infra failures and `0` model failures, and recorded bounded-launch H200 metrics up to `running_req=8` and `gen_throughput≈575.58 tok/s`

## 2026-04-20T17:28:00Z swe-qwen36-clean-eval-batch100-fastfix-run-20260420
- purpose: relaunch the same qwen36 batch100 clean eval with shared runtime cache, bounded launch concurrency, explicit ready gate, synthetic failure manifests, and clean-eval transport retry
- config: logs/real-tests/swe-qwen36-clean-eval-batch100-fastfix-run-20260420/README.txt
- workload: wrk-g94qk5jts0lk, wrk-cjrs8a2n9y9j
- machine: swe-h200-sglang-0418a, swe-cpu-large-central-0420a
- host: 72.46.85.157:30166, 72.46.85.157:32422
- status: running
- cleanup: current turn
- notes: the full run reuses the existing batch100 `selected_tasks.json` and `image_prewarm.json`; early bounded-launch state shows `4` tasks already in real rollout, `8` tasks in active bootstrap, and no `runtime_bootstrap_failed`, `student_transport_failed`, `openenv_failed`, or `launch_aborted` manifests so far; early H200 metrics show `running_req` reaching `7-8` with `gen_throughput≈671.85 tok/s`
