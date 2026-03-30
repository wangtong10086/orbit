# Long Collect Real Test — 4 Envs

Date: 2026-03-30
Repo target: `waston10086/test_data`

## Scope

Validate longer real collection runs for:

- `GAME`
- `NAVWORLD`
- `LIVEWEB`
- `MEMORYGYM`

`SWE-INFINITE` was intentionally masked out for this session.

## Key Outcome

- `NAVWORLD`: pass
- `LIVEWEB`: pass
- `MEMORYGYM`: pass after fixing `tier_mix` zero-work bug
- `GAME`: pass after switching the active trajectory generator to the new
  random generator registry path

## GAME Notes

The original `all-games` runs exposed that a single hard-coded generator path
was not stable across all 7 games:

- `liars_dice` could stall on unlucky seed blocks
- `gin_rummy` and spatial games were too slow on the old path for collection use

The collector was then refactored so `GAME` trajectory generation goes through
an explicit generator registry, with the current default set to the random
generator for every game.

Successful real run:

- Bundle: `tmp/bundle-collect-game-random`
- Log: `logs/real-tests/2026-03-30/long-collect-4env-logs/game-random.log`
- Result:
  - `goofspiel=2`
  - `leduc_poker=2`
  - `liars_dice=2`
  - `gin_rummy=2`
  - `othello=2`
  - `hex=2`
  - `clobber=2`
  - `collect.records=14`
  - `ingest.appended=14`
  - `mixed.rows=18278`

## NAVWORLD Notes

- Bundle: `tmp/bundle-collect-navworld-long`
- Log: `logs/real-tests/2026-03-30/long-collect-4env-logs/navworld.log`
- Result:
  - `collect.records=3`
  - `ingest.appended=3`
  - `mixed.rows=18244`

## LIVEWEB Notes

- Bundle: `tmp/bundle-collect-liveweb-long`
- Log: `logs/real-tests/2026-03-30/long-collect-4env-logs/liveweb.log`
- Result:
  - `records=3`
  - `errors=1`
  - `ingest.appended=3`
  - `mixed.rows=18247`
- Residual warning:
  - trailing `Unclosed client session` warning in log, but publish succeeded

## MEMORYGYM Notes

Initial run failed because `tier_mix` only counted `lite/standard` seeds but
only appended `hard` tiers into the worklist, yielding `0 trajectories` and a
division-by-zero on the summary print.

After the fix:

- Bundle: `tmp/bundle-collect-memorygym-long`
- Log: `logs/real-tests/2026-03-30/long-collect-4env-logs/memorygym.log`
- Result:
  - `collect.trajectories=6`
  - `collect.samples=18`
  - `ingest.appended=17`
  - `duplicates_skipped=1`
  - `mixed.rows=18264`

## Downstream Verification

`load_dataset("waston10086/test_data", "mixed", split="train", token=...)`
was rerun after the successful GAME random-trajectory publish.

Result:

- `rows=18278`
- envs: `GAME`, `LIVEWEB`, `MEMORYGYM`, `NAVWORLD`

## Logs

- Command log: `logs/real-tests/2026-03-30/long-collect-4env-logs/commands.txt`
- GAME logs:
  - `logs/real-tests/2026-03-30/long-collect-4env-logs/game.log`
  - `logs/real-tests/2026-03-30/long-collect-4env-logs/game-retry.log`
  - `logs/real-tests/2026-03-30/long-collect-4env-logs/game-random.log`
- NAVWORLD log:
  - `logs/real-tests/2026-03-30/long-collect-4env-logs/navworld.log`
- LIVEWEB log:
  - `logs/real-tests/2026-03-30/long-collect-4env-logs/liveweb.log`
- MEMORYGYM log:
  - `logs/real-tests/2026-03-30/long-collect-4env-logs/memorygym.log`
