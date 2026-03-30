# Five-Env Private Dataset Real Test

Date: 2026-03-30
Repo target: `waston10086/test_data` (private HF dataset repo)

## Scope

Validate real collection and publish behavior for:

- `NAVWORLD`
- `GAME`
- `MEMORYGYM`
- `LIVEWEB`
- `SWE-INFINITE`

This session used each environment's real collector path. It did not inject
synthetic remote SWE source files or manually patch bundle outputs.

## Runtime notes

- Official `forge worker run --runtime docker` validation is currently blocked
  on this host because the local Docker daemon socket is not accessible.
- The rendered bundle entrypoint was executed directly for collector validation,
  using the real `forge.data.collect_publish` path that the bundle runtime would
  invoke.

## Results

### NAVWORLD

- State: `pass`
- Bundle: `tmp/bundle-collect-navworld-5env`
- Outcome:
  - real sample generated
  - raw uploaded
  - canonical ingest appended `1`
  - mixed dataset rebuilt successfully

### GAME

- State: `pass`
- Bundle: `tmp/bundle-collect-game-5env`
- Outcome:
  - real sample generated for `goofspiel`
  - raw uploaded
  - canonical ingest appended `1`
  - mixed dataset rebuilt successfully

### MEMORYGYM

- State: `fail`
- Bundle: `tmp/bundle-collect-memorygym-5env`
- Outcome:
  - raw trajectory generation succeeded
  - split step succeeded and produced `5` samples
  - canonical ingest was rejected because every split sample was missing the
    top-level `score` field

### LIVEWEB

- State: `fail`
- Bundle: `tmp/bundle-collect-liveweb-5env`
- Outcome:
  - real live fallback collection succeeded
  - raw uploaded
  - canonical ingest was rejected because the generated record ended with a
    `tool` message instead of an `assistant` message

### SWE-INFINITE

- State: `blocked`
- Bundle: `tmp/bundle-collect-swe-5env`
- Outcome:
  - real sync path attempted against the configured default distillation host
  - remote access failed with `Permission denied (publickey)`
  - no new SWE data was collected

## Downstream verification

- `load_dataset("waston10086/test_data", "mixed", split="train", token=HF_TOKEN)`
  succeeded after force refresh
- Current mixed rows: `3`
- Current mixed envs: `GAME`, `NAVWORLD`

## Key blockers

1. `MEMORYGYM` split output is not canonical-ready because `score` is missing.
2. `LIVEWEB` live fallback can emit conversations whose last message is `tool`,
   which canonical validation rejects.
3. `SWE-INFINITE` cannot reach the real distillation source with current SSH
   credentials.
4. Local Docker runtime validation is blocked by Docker daemon socket
   permissions on this host.
