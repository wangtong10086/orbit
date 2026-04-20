# SWE Synthesis Pipeline

This document is a standalone explanation of the **current active** SWE
synthesis pipeline in ORBIT.

It is intentionally separate from:

- historical staged-search experiments under `logs/real-tests/`
- the broader repository architecture document
- old local `orbit/data/swe_collection/` implementations

The goal is to make the current pipeline understandable end-to-end:

- what ORBIT owns
- what upstream `affinetes` owns
- what runs on which machine
- how `student`, `teacher`, `OpenEnv`, `checkpoint`, `restore`, and `retry`
  fit together

This document describes the implementation that is active in code today.

## Scope

This document covers only the active path behind:

```bash
python3 -m orbit data swe-collect synthesize
```

It does **not** describe:

- `evaluate()`-only black-box swe collection
- historical ORBIT-side tree search / bucket pipelines
- generic training or evaluation flows outside SWE

## One-Sentence Mental Model

ORBIT runs a thin controller on top of upstream `AffineFoundation/affinetes`
OpenEnv for `SWE-INFINITE`; the controller asks a student model for one command
at a time, optionally asks a teacher model for a structured rollback / guidance
decision, uses upstream `checkpoint/restore` for retries, and records raw
events plus a small manifest.

## Ownership Boundaries

### ORBIT owns

- CLI surface: `orbit data swe-collect synthesize`
- exact-ref upstream checkout resolution
- runtime bootstrap for the upstream environment
- OpenEnv bridge process management
- student / teacher model calling
- retry / restore orchestration
- raw event logging and final run manifest

### Upstream `affinetes` owns

- `SWE-INFINITE` environment semantics
- task reset
- task step execution
- working-tree snapshotting through `checkpoint`
- restore behavior through `restore`
- task container lifecycle
- observation / reward / done / truncated payloads

### Student model owns

- proposing the next shell action

### Teacher model owns

- structured control decisions:
  - continue from `CURRENT`
  - restore `BASELINE`
  - roll back to one of the recent edit checkpoints
  - `STOP` the run
- optional hidden reasoning (`teacher think`) injected back into the next
  student prompt
- the teacher does **not** emit shell actions on the active path

## Primary Deployment Shape

The most important current deployment pattern is:

- one **CPU collector rental**
- one **GPU student-serving rental**
- one or more upstream **task containers** started by OpenEnv on the collector

Typical real setup:

- CPU rental runs:
  - ORBIT CLI
  - upstream affinetes checkout
  - OpenEnv server process
- GPU rental runs:
  - OpenAI-compatible student serving endpoint
- teacher is another OpenAI-compatible endpoint, which may be remote or hosted
  on a second GPU rental

## ASCII Architecture Diagram

```text
                               +----------------------+
                               |  Teacher endpoint    |
                               |  e.g. gpt-5.4        |
                               +----------+-----------+
                                          ^
                                          |
                                          | restore decision / hidden think
                                          |
+----------------------+         +--------+-------------------------------+
|  H200 / GPU rental   |         |         CPU / collector rental         |
|----------------------|         |----------------------------------------|
| OpenAI-compatible    | <-----> | ORBIT synth controller                 |
| student endpoint     |  HTTP   | - prompt building                      |
| e.g. SGLang or       |         | - student/teacher routing              |
| transformers serve   |         | - retry policy                         |
+----------------------+         | - event logging                         |
                                 |                                        |
                                 | OpenEnv bridge process                 |
                                 | - reset/state/checkpoint/restore/step  |
                                 +------------------+---------------------+
                                                    |
                                                    | local IPC / socket
                                                    v
                                 +------------------+---------------------+
                                 |    Upstream affinetes / SWE-INFINITE   |
                                 |----------------------------------------|
                                 | InfiniteActor + OpenEnv state          |
                                 | task resolution                        |
                                 | task container launch                  |
                                 | observation/reward/done                |
                                 +------------------+---------------------+
                                                    |
                                                    | docker exec / task runtime
                                                    v
                                 +----------------------------------------+
                                 | SWE task container                     |
                                 | repo under /app                        |
                                 | commands run here                      |
                                 | working tree changes live here         |
                                 +----------------------------------------+
```

## High-Level Flow

```text
1. User runs `orbit data swe-collect synthesize`
2. ORBIT resolves the exact upstream affinetes checkout
3. ORBIT starts an OpenEnv bridge process around upstream SWE-INFINITE
4. ORBIT calls upstream `reset(task_id)`
5. ORBIT creates a baseline checkpoint
6. ORBIT optionally probes runtime tool availability in the task container
7. ORBIT loops:
   - build prompt
   - optionally call the teacher for a structured control decision
   - maybe inject hidden teacher guidance into the next student prompt
   - call the student
   - materialize one shell action
   - call upstream `step(action)`
   - inspect new state
   - maybe checkpoint
   - maybe restore `BASELINE` or one of the recent edit checkpoints
   - maybe stop because the controller hit a loop budget or the teacher chose
     `STOP`
8. ORBIT writes:
   - `raw/synthesis_events.jsonl`
   - `manifests/synthesis_run.json`
9. ORBIT stops the OpenEnv episode and bridge
```

## Detailed Flow Diagram

```text
Start
  |
  v
Resolve exact upstream repo/ref
  |
  v
Bootstrap per-run runtime
  |
  v
Start OpenEnv bridge
  |
  v
openenv reset(task_id)
  |
  v
baseline checkpoint
  |
  +--> optional runtime probe
  |      |
  |      +--> detect python3 / python / ruby / perl
  |      +--> restore baseline after probe
  |
 v
Build first prompt
  |
  v
Optional teacher/controller decision
  |
  +--> restore_target = CURRENT / BASELINE / ROLLBACK_N / STOP
  +--> optional teacher_think_text
  |
  v
Call student model
  |
  v
step(action)
  |
  v
state()
  |
  +--> if changed_files != empty:
  |      +--> create post-edit checkpoint
  |
  +--> if no-progress / repeated reads / repeated verify / bad patch lineage:
  |      +--> maybe teacher decision
  |      +--> maybe teacher-think
  |      +--> maybe restore(baseline or one of the recent edit checkpoints)
  |      +--> maybe stop
  |
  +--> if max_steps reached or done/truncated:
  |      +--> stop
  |
  +--> else:
         loop to next prompt
```

## Sequence Diagram

```text
User/CLI
  |
  | synthesize(task_id, model, teacher, output_dir)
  v
ORBIT Synth Controller
  |
  | prepare_upstream_runtime()
  v
OpenEnv Bridge
  |
  | reset(task_id)
  v
Upstream SWE-INFINITE
  |
  | create task container
  v
Task Container

ORBIT Synth Controller
  |
  | checkpoint("baseline")
  v
Upstream SWE-INFINITE

ORBIT Synth Controller
  |
  | step(runtime probe command)        [optional]
  v
Task Container
  |
  | output available interpreters
  v
ORBIT Synth Controller
  |
  | restore(baseline)                  [optional]
  v
Upstream SWE-INFINITE

ORBIT Synth Controller
  |
  | call student(model prompt)
  v
Student Endpoint
  |
  | one shell action
  v
ORBIT Synth Controller
  |
  | step(action)
  v
Task Container
  |
  | observation / reward / done
  v
ORBIT Synth Controller
  |
  | state()
  v
Upstream SWE-INFINITE
  |
  | changed_files / patch_hash / step_count
  v
ORBIT Synth Controller
  |
  | if stalled -> call teacher or teacher-think
  v
Teacher Endpoint
  |
  | next action or hidden guidance
  v
ORBIT Synth Controller
  |
  | maybe checkpoint / maybe restore / next loop
  v
...
  |
  | stop()
  v
Upstream SWE-INFINITE
```

## The Active Components In Code

### CLI entrypoint

- [orbit/cli_data.py](../orbit/cli_data.py)

This wires:

- `orbit data swe-collect synthesize`
- student endpoint flags
- teacher endpoint flags
- retry flags
- output directory

### Thin integration layer

- [orbit/integrations/affinetes_swe/runner.py](../orbit/integrations/affinetes_swe/runner.py)
- [orbit/integrations/affinetes_swe/openenv_server.py](../orbit/integrations/affinetes_swe/openenv_server.py)
- [orbit/integrations/affinetes_swe/synthesis.py](../orbit/integrations/affinetes_swe/synthesis.py)

Responsibilities:

- `runner.py`
  - resolve upstream repo
  - bootstrap per-run runtime
  - manage bridge IPC
  - expose `openenv_reset/state/checkpoint/restore/step/stop`
- `openenv_server.py`
  - wrap upstream actor in a long-lived bridge process
- `synthesis.py`
  - build prompts
  - call student/teacher models
  - decide when to retry or restore
  - write raw events and final manifest

## Per-Run Runtime Layout

For each synth run, ORBIT creates a run directory like:

```text
<output_dir>/
  raw/
    synthesis_events.jsonl
  manifests/
    synthesis_run.json
  .runtime/
    affinetes/        # cloned or linked upstream repo
    venv/             # per-run runtime venv
    home/
    openenv_ready.json
```

Key rule:

- ORBIT does not modify upstream semantics
- the run-local `.runtime/` directory only exists to execute upstream code

## Inputs to the Controller

The controller receives:

- `task_id`
- `student model`
- `student api base`
- `student api key`
- optional `teacher model`
- optional `teacher api base`
- optional `teacher api key`
- exact upstream git ref
- `max_steps`
- `max_root_retries`
- `max_edit_retries`
- `probe_runtime`
- `inject_teacher_think`
- `student_enable_thinking`

## Prompt Construction

Each step prompt is built from:

- issue / PR description extracted from the reset observation
- latest environment feedback
- remembered no-progress commands
- remembered viewed file / candidate file
- current runtime preference (`python3`, `perl`, `python`, `ruby`, or `sed`)
- optional hidden teacher-think text

There are two main prompt modes:

- **student mode**
- **teacher mode**

The teacher uses a stricter system prompt that is intended to produce one next
action rather than free-form planning.

## Student and Teacher Call Policy

### Student

The student is the default action generator.

Current behavior:

- call `responses.create(...)` first
- if the endpoint rejects or does not support it, fall back to
  `chat.completions.create(...)`

Current compatibility handling includes:

- `404` -> fall back to `chat.completions`
- `5xx` -> fall back to `chat.completions`
- `422` complaining about `enable_thinking` -> retry without the field

### Teacher

The teacher is used when the controller decides the student is stalled or the
current patch lineage needs a rollback / continue decision.

Common triggers:

- repeated no-progress commands
- command-not-found style failures
- syntax-error style edit failures
- already-edited working tree that now needs targeted continuation or rollback

## Teacher Think Injection

If enabled:

- the controller asks the teacher for short hidden guidance text
- the guidance is injected into the next student prompt
- this is separate from any shell-action generation, which remains student-only

The teacher-think channel is meant to guide the student without immediately
replacing it.

## Runtime Probe and Preferred Edit Runtime

If `--probe-runtime` is enabled, the controller first runs a lightweight probe
inside the task container to detect:

- `python3`
- `python`
- `ruby`
- `perl`

The probe result is converted into a preferred edit runtime:

```text
python3 > perl > python > ruby > sed
```

The prompt then tries to steer edit commands toward the best available
interpreter.

## Checkpoint / Restore Semantics

The controller uses upstream checkpointing in two main ways.

### Baseline checkpoint

Created right after reset.

Purpose:

- recover from a bad first move
- support `root retry`

### Post-edit checkpoint

Created after the controller sees real file changes.

Purpose:

- retry follow-up actions without losing the existing patch
- support `edit retry`

### Restore scopes

```text
baseline restore:
  go back to clean working tree after bad root exploration

post-edit restore:
  go back to the best current patch after a bad follow-up step
```

## Retry Logic

The controller has two explicit retry budgets.

### Root retry

Used when:

- early exploration produced no useful progress
- the controller wants to restore the clean baseline and try another first move

### Edit retry

Used when:

- there is already a patch
- a follow-up action fails or stalls
- the controller restores the post-edit checkpoint and tries another follow-up

## Recorded Artifacts

### Raw events

`raw/synthesis_events.jsonl` is the most important artifact.

It records a chronological event stream such as:

- `reset`
- `checkpoint`
- `runtime_probe`
- `restore`
- `model_action`
- `step`
- `state`
- `stop`
- `teacher_think`

This is the best file to read when debugging a run.

### Final manifest

`manifests/synthesis_run.json` summarizes the run state, including:

- `task_id`
- `episode_id`
- `student_calls`
- `teacher_calls`
- `teacher_think_calls`
- retry counts
- runtime availability
- preferred runtime
- latest changed files
- `final_reward`
- `verified_success`
- `final_test_stats`
- `model_stop_reason`
- `student_transport`
- `student_finish_reason_type`
- `student_finish_reason_length`
- `student_max_new_tokens`
- final observation

Notes:
- `final_reward` is taken from the terminal upstream `step` payload when the episode ends.
- `final_done=true` means upstream accepted a submission / terminal step; it does not imply `verified_success=true`.

## What Counts As A Successful Trajectory?

At minimum, a useful trajectory should eventually reach:

- real source-file edits
- meaningful follow-up actions
- ideally verification or a staged submit patch

Current stronger milestone:

- a trajectory that edits the correct source file
- and ends in a valid patch / verified success

## Current Failure Modes

The current pipeline is active and usable, but there are still important
failure modes.

### 1. Observation text can be mistaken for a file path

Example:

- `echo "No main.go found"`

This text can currently be misinterpreted by the controller as a viewed file,
which then contaminates teacher prompts.

### 2. Teacher can be locked onto a false target

Once the controller believes a fake file was already inspected, the teacher is
prompted to keep editing that target instead of re-checking the true file.

### 3. Different model servers support different OpenAI-compatible subsets

Examples:

- some student servers do not implement `/v1/responses`
- some reject `enable_thinking`
- some return `5xx` on `responses.create` but still work through
  `chat.completions`

### 4. Upstream OpenEnv reset can still be fragile

Some runs still fail during:

- task container start
- bridge initialization
- OpenEnv reset / IPC

## Practical Debugging Recipe

When a run looks wrong, inspect in this order:

1. `launch.log`
2. `raw/synthesis_events.jsonl`
3. `manifests/synthesis_run.json`

Recommended questions:

1. Did `reset` succeed?
2. Was the runtime probe correct?
3. Did the first `model_action` make sense?
4. Did the controller switch to teacher too late or too early?
5. Did `changed_files` point to a real source file?
6. Did a restore happen when it should have?

## Current Reality Summary

Today the pipeline is:

- real
- remote-capable
- checkpoint-aware
- teacher-aware
- artifacted

It is **not** yet consistently producing correct SWE patches.

The most important point for understanding is:

- ORBIT is **not** the SWE environment
- ORBIT is the **controller and recorder**
- upstream `affinetes` is the environment
- the student and teacher models only choose the next action

## Related Documents

- [architecture.md](architecture.md)
- [cli.md](cli.md)
- [testing.md](testing.md)
- [test-runbook.md](test-runbook.md)
