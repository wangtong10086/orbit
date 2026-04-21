# SWE Collection System: Architecture, Queues, and Bottlenecks

This document explains the **current active** SWE collection/eval system in
ORBIT from the perspective of system architecture and performance.

It is intentionally different from:

- [architecture.md](architecture.md), which describes repository-level
  architecture and ownership boundaries
- [swe-synthesis-pipeline.md](swe-synthesis-pipeline.md), which focuses on the
  active synth controller logic

This document answers a different question:

> What is the real end-to-end system that is currently running, where do the
> queues live, and where does time actually go?

## Scope

This document covers the active large-batch SWE path driven by:

- `python3 -m orbit data swe-collect synthesize`
- `scripts/swe_launch_batch.py`
- `orbit/integrations/affinetes_swe/batch_launcher.py`

It focuses on the current deployment shape used in real runs:

- one CPU collector rental
- one GPU student-serving rental
- upstream `affinetes` `SWE-INFINITE`
- OpenEnv bridge
- bounded streaming batch launcher

It does **not** describe:

- historical local ORBIT-side tree-search SWE pipelines
- generic ORBIT training/eval flows outside SWE
- the teacher-assisted synth policy details except where they matter for system
  shape

## One-Sentence Mental Model

The active SWE system is a **streaming, queue-driven control loop**:

- ORBIT runs a batch launcher on a CPU collector
- the launcher keeps image pull, bootstrap, warm-ready, and rollout stages
  filled
- each task eventually reaches a thin synth/eval controller process
- that process talks to upstream OpenEnv on the collector and to a student
  model endpoint on a GPU rental

The most important performance fact is:

- the GPU is **not always the bottleneck**
- the front-end supply path (`image -> bootstrap -> warm_ready -> rollout`) is
  often the real limiter

## Current Deployment Shape

```text
+--------------------------+                 +---------------------------+
| Local control machine    |                 | GPU rental (H200)         |
|--------------------------|                 |---------------------------|
| human operator           |                 | OpenAI-compatible student |
| repo edits               |                 | server (Qwen / SGLang)    |
| ssh / restart / inspect  |                 | cuda graph + radix cache  |
+------------+-------------+                 +-------------+-------------+
             |                                                 ^
             | ssh / sync / tunnel                             |
             v                                                 | HTTP
+------------+-------------------------------------------------+----------+
| CPU collector rental                                                     |
|--------------------------------------------------------------------------|
| batch launcher                                                           |
| - selected_tasks.json                                                    |
| - image pull queue                                                       |
| - bootstrap queue                                                        |
| - warm_ready release                                                     |
| - campaign_state.json / campaign_metrics.jsonl                           |
|                                                                          |
| per-task synth/eval controller processes                                 |
| - prompt build                                                           |
| - transport retry                                                        |
| - event logging                                                          |
| - manifest writing                                                       |
|                                                                          |
| OpenEnv bridge processes                                                 |
| - stateful socket bridge around upstream Actor                           |
|                                                                          |
| upstream affinetes checkout                                              |
| - SWE-INFINITE env                                                       |
| - reset / state / checkpoint / restore / step / stop                     |
|                                                                          |
| Docker daemon                                                            |
| - image inspect / pull                                                   |
| - container create / run / exec                                          |
+-------------------------------+------------------------------------------+
                                |
                                v
                    +-----------+----------------+
                    | task containers            |
                    |----------------------------|
                    | repo at /app               |
                    | commands execute here      |
                    | verifier/reward lives here |
                    +----------------------------+
```

## Main Components

### 1. Batch launcher

Primary file:

- `orbit/integrations/affinetes_swe/batch_launcher.py`

Responsibilities:

- enforce student ready gate before launch
- maintain queue state for thousands of tasks
- smooth image pull and bootstrap dispatch
- release warm-ready runs into active rollout
- record campaign-level metrics and state
- classify terminal manifests into:
  - `completed`
  - `failed_infra`
  - `failed_model`

### 2. Thin synth/eval controller

Primary file:

- `orbit/integrations/affinetes_swe/synthesis.py`

Responsibilities:

- per-task reset/checkpoint/step loop
- model call transport
- event logging
- manifest writing
- clean-eval semantics
- optional synth-controller behavior above OpenEnv

### 3. Upstream runtime bootstrap

Primary file:

- `orbit/integrations/affinetes_swe/runner.py`

Responsibilities:

- resolve task payloads from cache
- resolve task image tags
- prewarm and image helpers
- shared immutable upstream runtime cache
- OpenEnv request helpers

### 4. OpenEnv bridge

Primary file:

- `orbit/integrations/affinetes_swe/openenv_server.py`

Responsibilities:

- wrap upstream `env.Actor`
- expose `reset/state/checkpoint/restore/step/stop` over local IPC
- reuse local images when present
- apply startup patches needed for concurrent stateful execution

## Queue Model

The active launcher is best understood as a **multi-stage queue system**.

### Task states

Current launcher states:

- `pending`
- `bootstrapping`
- `warm_ready`
- `running`
- `completed`
- `failed_infra`
- `failed_model`

### Queue layers

```text
selected_tasks.json
      |
      v
[pending tasks]
      |
      | needs image ready
      v
[image pull queue] ----> [prefetched / ready pending]
      |
      | image ready
      v
[bootstrap queue]
      |
      | openenv server + reset + baseline checkpoint
      v
[warm_ready]
      |
      | rollout release
      v
[running rollout]
      |
      +--> done / model_stop / context_limit / ...
      +--> launch_aborted / student_transport_failed / ...
```

### Why `warm_ready` exists

`warm_ready` means:

- OpenEnv is alive
- `reset` succeeded
- baseline `checkpoint` succeeded
- but the first `model_action` has **not** been released yet

This allows the launcher to keep a small ready buffer so that active rollout
slots do not need to wait for a cold bootstrap every time a task finishes.

## Per-Task Lifecycle

### End-to-end sequence

```text
batch launcher
    |
    | launch synth process
    v
synth/eval controller
    |
    | start OpenEnv bridge
    v
openenv_server
    |
    | reset(task_id)
    v
upstream SWE-INFINITE
    |
    | docker run task container
    v
task container

synth/eval controller
    |
    | checkpoint("baseline")
    v
upstream SWE-INFINITE

synth/eval controller
    |
    | write bootstrap_ready.json
    | wait for rollout release file
    v
batch launcher
    |
    | release warm_ready slot
    v
synth/eval controller
    |
    | chat.completions(student)
    v
H200 student server
    |
    | action text
    v
synth/eval controller
    |
    | step(action)
    v
upstream SWE-INFINITE
    |
    | run command in task container
    v
task container

synth/eval controller
    |
    | state / inspect reward / loop
    | write raw event
    | maybe write final manifest
    v
batch launcher observes manifest
```

### Flowchart

```text
pending
  |
  | image ready?
  v
bootstrap queue
  |
  | launch synth process
  v
bootstrapping
  |
  | openenv_server ready
  | reset
  | baseline checkpoint
  v
warm_ready
  |
  | launcher releases rollout slot
  v
running
  |
  +--> first model_action
  +--> step/state loop
  +--> manifest written
  |
  +--> terminal_status in:
         - done / truncated
         - model_stop / context_limit / max_steps
         - launch_aborted / student_transport_failed / openenv_failed
  v
completed / failed_infra / failed_model
```

## What the Student Server Actually Does

The student model does **not** own the whole task.

The student server only owns:

- action generation
- next-step reasoning and command text

The rest of the system is elsewhere:

- image management: launcher + Docker
- environment lifecycle: OpenEnv + upstream `affinetes`
- repo mutation and verification: task container + upstream verifier
- batching/backfill/metrics: launcher

That is why GPU throughput can improve while end-to-end collection rate does
not improve by the same factor.

## Why the System Can Look Idle Even When It Is Slow

This is the most confusing part of the current system.

Observed collector resource profile in real runs:

- CPU mostly idle
- memory mostly free
- disk I/O wait near zero

Observed student-side profile in good windows:

- H200 `#running-req` can become high
- generation throughput can exceed `1k tok/s`

Yet collection can still feel slow.

The reason is that the slow path is dominated by **control-plane tail
latency**, not by saturated compute:

- `docker image inspect`
- `docker pull`
- `docker run`
- `reset`
- `baseline checkpoint`

These are short, stateful control operations with poor tail behavior under
concurrency. They do not necessarily drive high average CPU or I/O
utilization, but they still hold up the pipeline.

## Current Performance Model

The active system has three major stages:

### A. Image availability

Inputs:

- task payload
- Docker image tag

Output:

- image locally available on the collector

Important current reality:

- the current large Codex SWE manifest has effectively **one unique image per
  task**
- in a recent 1872-task run:
  - `task_count = 1872`
  - `unique_images = 1872`

This means image reuse is close to zero for that dataset.

Implication:

- image streaming can easily become a registry-rate-limit problem
- even if local CPU and disk are not saturated

### B. Bootstrap

Inputs:

- image is local
- task is ready to launch

Output:

- `warm_ready`

Bootstrap covers:

- OpenEnv bridge startup
- upstream `reset`
- baseline `checkpoint`

Observed timing in real runs:

- `launch_started_at -> bootstrap_ready_at`: about `223s` average
- `bootstrap_ready_at -> first_model_action_at`: about `5s`

This is the strongest evidence that **bootstrap is often the real front-end
bottleneck**.

### C. Rollout

Inputs:

- released `warm_ready` task

Output:

- final manifest

In good windows, the H200 can sustain much more load than the launcher is able
to feed continuously. That is why the GPU is not always the primary limiter.

## Current Bottlenecks

### Bottleneck 1: unique-image pressure

Problem:

- the dataset has almost no image reuse
- even authenticated Docker Hub pulls can hit rate limits under sustained
  streaming

Symptoms:

- `launch_aborted`
- Docker Hub `toomanyrequests`
- rising `failed_infra` while CPU is still mostly idle

Why queueing helps but does not solve it:

- queueing smooths the request burst
- queueing does **not** reduce the total number of unique images that must be
  fetched

### Bottleneck 2: bootstrap tail latency

Problem:

- `docker run`, `reset`, and `checkpoint` have high tail latency
- these operations hit Docker/OpenEnv control paths, not a simple CPU-bound
  worker pool

Symptoms:

- increasing bootstrap concurrency too aggressively causes:
  - `docker run` timeout
  - `launch_aborted`
  - unstable front-end supply

Why this is not contradicted by low CPU usage:

- control-path latency can be high even when average CPU is low
- Docker/OpenEnv lifecycle operations are not linearly scalable with process
  count

### Bottleneck 3: thin warm-ready buffer

Problem:

- if `warm_ready` stays near zero, every finished rollout needs the next task
  to wait for cold bootstrap

Symptoms:

- H200 `running-req` oscillates
- rollout count drops even when many tasks are still queued
- queue metrics show:
  - high `queued_image_pulls`
  - some `active_bootstraps`
  - very low `warm_ready`

## What Is *Not* the Main Bottleneck Right Now

### Not average CPU saturation

Observed collector snapshots repeatedly showed:

- many idle cores
- low system usage

### Not memory pressure

Collector memory was far from full in real runs.

### Not disk I/O saturation

Observed `wa` was near zero in healthy windows.

### Not always the H200

In the best windows, the H200 can run significantly ahead of the front-end
supply rate. That means more GPU alone does not automatically solve the
problem.

## Why Increasing Bootstrap Concurrency Can Backfire

This is worth stating directly.

Naive intuition:

- bootstrap is slow
- therefore just increase bootstrap concurrency

What actually happens:

- the slow section is not a pure compute worker
- it is a Docker/OpenEnv lifecycle path with shared control-plane bottlenecks
- pushing too many tasks through that path at once raises tail latency and
  timeout rates

That is why the system now uses:

- bounded queues
- dispatch bursts
- separate image and bootstrap stages

Instead of:

- launching all pending tasks at once

## Why Increasing Overall In-Flight Work Still Makes Sense

The correct way to hide tail latency is **not** to smash the fragile stage with
unbounded concurrency.

The correct way is:

- keep many tasks in flight across different stages
- keep queues thick enough that rollout does not stall
- keep the fragile stage smoothed and bounded

In other words:

- raise total in-flight work
- but keep the most failure-prone stage rate-limited

## Practical Scaling Guidance

### If you want higher throughput on one collector

Most promising levers:

1. Keep image streaming ahead of rollout, but smooth it.
2. Maintain a thicker `warm_ready` buffer.
3. Increase total in-flight work without sharply increasing bootstrap burst.
4. Reduce bootstrap tail latency rather than only increasing bootstrap count.

### If you want meaningfully higher total throughput

The cleanest next architectural step is:

- keep one or more H200s for student serving
- split bootstrap across multiple CPU collectors

Reason:

- GPU serving and Docker/OpenEnv bootstrap are different resource problems
- multiple collectors reduce control-plane contention better than forcing one
  collector to handle all container lifecycle work

### If you want to eliminate the registry problem

Most effective fixes:

1. registry mirror or private registry
2. authenticated pulls with sufficient quota
3. bulk prewarm in an environment with higher registry capacity

Queueing alone is not enough when each task uses a unique image.

## Reading the Metrics

When looking at a live campaign, interpret these fields as follows:

- `active_rollouts`
  - tasks that already crossed the first `model_action`
- `active_bootstraps`
  - tasks currently in `openenv_server + reset + checkpoint`
- `warm_ready`
  - tasks ready to roll but not yet released
- `ready_pending`
  - pending tasks whose images are already ready
- `prefetched_pending`
  - pending tasks whose images are either ready or currently pulling
- `started_per_min`
  - front-end release velocity into rollout
- `completed_per_min`
  - terminal manifest velocity
- `h200_running_req`
  - current concurrent requests seen by the student server
- `h200_gen_throughput`
  - current generation throughput from the student server

## Debugging Checklist

When the system is slow, ask these questions in order:

1. Is the launcher alive?
2. Is `failed_infra` increasing?
3. Is `warm_ready` near zero?
4. Is `ready_pending` high but `active_bootstraps` low?
5. Is `active_bootstraps` high but `bootstrap_ready_at` slow?
6. Is `h200_running_req` low because rollout supply is thin?
7. Are failures coming from:
   - Docker Hub rate limit?
   - image inspect timeout?
   - docker run timeout?
   - reset/checkpoint failures?

This ordering helps separate:

- registry problems
- bootstrap problems
- rollout/GPU utilization problems

## Bottom Line

The current SWE collection system is not a simple “GPU inference job”.

It is a **staged distributed system** with:

- a registry-bound image layer
- a Docker/OpenEnv bootstrap layer
- a GPU action-generation layer
- a bounded launcher that tries to keep all three balanced

The two most important facts to remember are:

1. **Bootstrap is often the immediate front-end bottleneck.**
2. **Registry pressure becomes the long-run stability bottleneck when the task
   set has one unique image per task.**

If you keep those two facts in mind, most of the observed behavior in large SWE
collection runs becomes much easier to understand.
