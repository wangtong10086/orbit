# Pydantic Validation Guide

This guide explains where Pydantic fits into ORBIT and how to debug failures
that come from contracts, schema validation, or input normalization.

The short version:

- Pydantic in this repository is about contracts and validation
- it is not a logging subsystem
- `logging.jsonl` is a training metrics log, not a Pydantic log

## Where Pydantic Is Used

ORBIT uses Pydantic for cross-module contracts and strict schema boundaries.

Important repository surfaces include:

- `orbit/foundation/schema.py`
  - strict model defaults and shared schema helpers
- `orbit/foundation/data_contracts.py`
  - canonical data contracts and validation helpers
- other control, execution, and task contract modules under `orbit/core/` and
  adjacent package APIs

Pydantic is most relevant when a failure happens before a real runtime or
training command is underway.

## What A Pydantic Failure Usually Looks Like

Typical signs:

- the command fails during parsing or object construction
- the traceback mentions validation, fields, schema, or type conversion
- the failure happens before useful `training.log` output exists
- the error points at a config field or data shape rather than a runtime import

Typical examples:

- a required field is missing
- a field has the wrong type
- a value violates a validator or normalization rule
- a canonical data record does not match the declared schema

## How To Distinguish It From Runtime Logging Problems

Use this rule:

- if the command never reaches the real bundle workload, suspect validation
- if the bundle launches and writes task/runtime logs, suspect runtime behavior

Quick split:

| Symptom | More likely category |
| --- | --- |
| traceback mentions `pydantic`, `ValidationError`, field names, or schema paths | contract/schema validation |
| `runtime-precheck.log` shows import failures | runtime environment |
| `training.log` shows stack traces or OOM | training/runtime behavior |
| `logging.jsonl` exists and has real steps | runtime got far enough to train |

## Where To Read Next In The Code

If you are debugging a contract failure, inspect the model that owns the
boundary rather than searching task logs first.

Start from the relevant command or workflow and then locate:

- the request model or config model
- the validator or normalizer
- the boundary where external/user input becomes an internal model

Good first places:

- `orbit/foundation/schema.py`
- `orbit/foundation/data_contracts.py`
- the contract module nearest the failing workflow under `orbit/core/contracts/`
  or the relevant package `api.py`

## Practical Debugging Workflow

### Case 1: A config-driven command fails immediately

Do this:

1. read the CLI traceback
2. identify the failing field or model
3. inspect the owning schema/contract model
4. only after that move to runtime logs if the command gets past validation

### Case 2: Canonical data validation fails

Do this:

1. identify which input record or field failed
2. inspect the canonical model in `orbit/foundation/data_contracts.py`
3. confirm whether the failure is a missing field, wrong type, or validator rule

### Case 3: A reader says "the Pydantic logs are wrong"

Correct interpretation:

- there usually are no dedicated validation log files owned by Pydantic itself
- there is a validation error surface
- there are separate runtime and training logs

Point them to:

- this guide for contract/schema failures
- [logging-and-artifacts.md](logging-and-artifacts.md) for actual log files

## Terminology Rules For Future Docs

Use these terms consistently:

- `Pydantic validation`
- `contract/schema error`
- `training metrics log` for `logging.jsonl`
- never `Pydantic log`

## Related Guides

- [debugging.md](debugging.md)
- [logging-and-artifacts.md](logging-and-artifacts.md)
