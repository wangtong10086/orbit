# Third-Party Notices

This repository ships third-party dependencies. This file documents the
current dependency declaration points and upstream provenance notes that remain
relevant for the public repository.

## Dependency Declarations

ORBIT declares its direct Python dependencies in:

- [pyproject.toml](pyproject.toml)
- [uv.lock](uv.lock)

The current top-level dependency groups are:

- core install: `click`, `pydantic`, `pydantic-settings`, `PyYAML`
- `control` extra: network/API clients such as `aiohttp`, `httpx`,
  `huggingface_hub`, `openai`, `anthropic`, `nest-asyncio`
- `exec` extra: training/runtime packages such as `transformers`, `datasets`,
  `accelerate`, `peft`, `trl`, `bitsandbytes`, `ms-swift`, `deepspeed`,
  `wandb`, plus the API clients used by distillation backends
- `all` extra: `control + exec`

`uv.lock` is the reproducible resolution used for development and CI. The lock
file is generated data; the normative declaration remains `pyproject.toml`.

Each dependency remains subject to its own upstream license and terms.

## Vendored and Modified Upstream Code

The current public repository snapshot does not ship vendored third-party
source code. Training and distillation use upstream `ms-swift` directly,
including native `swift rlhf --rlhf_type gkd` for the public distillation
workflow.

## Policy For New Vendored Code

If new third-party source code is added to this repository:

- record the upstream project name and URL
- record the upstream license
- describe the local modification scope
- update this file and [NOTICE](NOTICE)
- keep the vendored area minimal and auditable
