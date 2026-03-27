# Affine-Swarm Architecture

Three-layer architecture for iterative LLM training on Bittensor Subnet 120.

> For practical code examples, see [usage-examples.md](usage-examples.md).
> For the detailed Chinese architecture report, see [architecture-report.md](architecture-report.md).

## Layer 0 — Foundation (zero cross-deps)

Three independent modules. Each depends only on Python stdlib.

### `forge/env/` — Environment Definitions

Three separated interfaces following [ROCK](https://github.com/alibaba/ROCK)'s architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                        EnvHub                               │
│               (unified registry, analogous to ROCK EnvHub)  │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  Sandbox API │  │   GEM API    │  │    Data API       │  │
│  │  (runtime)   │  │ (interaction)│  │  (validation)     │  │
│  │              │  │              │  │                   │  │
│  │ SandboxConfig│  │   GemEnv     │  │   EnvProtocol     │  │
│  │ Sandbox      │  │  reset()     │  │  validate_entry() │  │
│  │  start()     │  │  step()      │  │  clean_entry()    │  │
│  │  execute()   │  │  close()     │  │  deep_validate()  │  │
│  │  stop()      │  │              │  │  prompt_builder()  │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**Sandbox API** (`sandbox.py`) — Runtime lifecycle management:

| Type | Purpose |
|------|---------|
| `SandboxConfig` | Container/VM config: image, memory, cpus, gpu, timeout, env_vars |
| `SandboxStatus` | Lifecycle states: CREATED → STARTING → RUNNING → STOPPING → STOPPED |
| `ExecutionResult` | Command result: stdout, stderr, exit_code, timed_out |
| `Sandbox` | Runtime manager: `start()` → `execute(cmd)` → `stop()` |

**GEM API** (`gem.py`) — Interactive environment protocol (analogous to ROCK's GEM):

| Type | Purpose |
|------|---------|
| `Observation` | Agent-visible state: text + metadata dict |
| `StepResult` | Step result: observation, reward, terminated, truncated, info; `as_tuple()` |
| `GemEnv` | Base class: `reset(seed)` → `step(action)` → `close()`; `is_interactive` property |

**Data API** (`base.py`) — Offline SFT data validation:

| Type | Purpose |
|------|---------|
| `EnvSpec` | Environment metadata: name, version, task_count, scoring_weight, valid_roles |
| `EnvProtocol` | Data validator: `validate_entry()`, `clean_entry()`, `deep_validate()`, `prompt_builder()` |

**Registry** (`registry.py`) — Dual registry:

| Type | Purpose |
|------|---------|
| `EnvRegistry` | Backward-compatible data validator registry (`@register`, `make`, `list_envs`) |
| `EnvHub` | Unified hub: `make_data()`, `make_gem()`, `list_all()`, `has_gem()` |

**Per-environment files** — Each file registers both a data validator and a GEM env:

| File | Data Class | GEM Class | Key Rules |
|------|-----------|-----------|-----------|
| `game.py` | `GameEnv` | `GameGemEnv` | weight=3.0, ≥3 msgs, system first |
| `navworld.py` | `NavworldEnv` | `NavworldGemEnv` | ≥7 msgs, ≥3 tool calls, final ≥200 chars |
| `swe.py` | `SweEnv` | `SweGemEnv` | ≥4 msgs, system first |
| `liveweb.py` | `LivewebEnv` | `LivewebGemEnv` | ≥3 msgs, has assistant, allows tool role |
| `lgc.py` | `LgcEnv` | `LgcGemEnv` | Exactly 2 msgs, balanced think tags |
| `print_env.py` | `PrintEnv` | `PrintGemEnv` | Exactly 2 msgs, answer after think |

Usage:
```python
from forge.env import EnvHub, EnvRegistry
import forge.env.game  # triggers registration

# Data validation (existing workflow)
validator = EnvHub.make_data("GAME")
issues = validator.validate_entry(record)
cleaned = validator.clean_entry(record)

# GEM interactive protocol (new)
env = EnvHub.make_gem("GAME")
obs, info = env.reset(seed=42)
result = env.step("e2e4")
obs, reward, terminated, truncated, info = result.as_tuple()
env.close()

# Sandbox lifecycle (new)
from forge.env import Sandbox, SandboxConfig
sandbox = Sandbox(SandboxConfig(image="python:3.11", memory="16g"))
await sandbox.start()
result = await sandbox.execute("python eval.py")
await sandbox.stop()
```

### `forge/prompt/` — Prompt Engine

| File | Exports | Purpose |
|------|---------|---------|
| `builder.py` | `PromptBuilder`, `Message` | Fluent API for building OpenAI-format message lists |
| `tools.py` | `load_tools`, `tool_names`, `get_tool_schema` | Load tool JSON from templates dir |
| `templates/` | `.md` + `.json` files | Per-env system prompts and tool schemas |

Usage:
```python
from forge.prompt.builder import PromptBuilder

pb = PromptBuilder("game")
msgs = pb.system("system", game_name="chess").user("Your move").build()
```

### `forge/training/` — Training Backend

| File | Exports | Purpose |
|------|---------|---------|
| `config.py` | `TrainConfig` | Dataclass with all SFT hyperparams + `to_train_script()` |
| `backend.py` | `TrainBackend` | Protocol: `generate_script()`, `validate_config()` |
| `sft.py` | `SftBackend` | SFT implementation of TrainBackend |
| `model.py` | `merge_lora_adapter`, `get_hf_latest_revision` | Model management utilities |
| `executor/` | `ExecutorProtocol`, `TargonExecutor`, `RemoteExecutor` | Compute backends |

## Layer 1 — Application (depends on Layer 0)

### `forge/pipeline/`

| File | Class | Purpose |
|------|-------|---------|
| `data.py` | `DataPipeline`, `IngestReport` | Ingest flow: clean → validate → dedup → store → export |
| `eval.py` | `Evaluator`, `EvalReport`, `EnvResult` | Evaluation orchestration, geo mean computation |
| `experiment.py` | `ExperimentTracker`, `Experiment` | YAML-based experiment lifecycle management |

## Layer 2 — Agent (depends on Layer 1)

### `forge/agent/`

| File | Class | Purpose |
|------|-------|---------|
| `base.py` | `AgentProtocol`, `StepResult` | sense → plan → act → reflect cycle |
| `strategist.py` | `StrategistAgent`, `GapAnalysis` | Gap analysis, experiment design, method switching |
| `trainer.py` | `TrainerAgent` | Validates experiments, orchestrates training→eval |
| `data_agent.py` | `DataAgent` | Data preparation, quality audit, sufficiency checks |
| `loop.py` | `EvolutionLoop`, `StepResult` | Full self-evolution cycle orchestrator |

## Dependency Graph

```
Layer 2: agent/strategist ─→ pipeline/experiment
         agent/trainer    ─→ pipeline/eval, training/sft
         agent/data_agent ─→ pipeline/data, env/registry
         agent/loop       ─→ agent/*

Layer 1: pipeline/data    ─→ env/registry
         pipeline/eval    ─→ env/registry
         pipeline/experiment ─→ (stdlib only: yaml, pathlib)

Layer 0: env/sandbox.py   ─→ (stdlib only: dataclasses, enum, hashlib)
         env/gem.py       ─→ env/base (EnvSpec)
         env/registry.py  ─→ env/base (EnvProtocol), env/gem (GemEnv)
         env/*.py         ─→ env/base, env/gem, env/registry
         prompt/*         ─→ (stdlib only)
         training/*       ─→ (stdlib only, except model.py uses transformers)
```

## Backward Compatibility

- `forge/data/sft.py` — delegates `_clean_*` functions to `EnvRegistry`
- `forge/data/canonical_ops.py` — uses `_get_valid_roles()` / `_get_allowed_extra()` backed by registry
- `forge/deploy.py` — imports `merge_lora_adapter`, `get_hf_latest_revision` from `forge.training.model`
