# Affine Swarm — Usage Examples

Practical examples for each layer of the three-layer architecture.

---

## Layer 0: Environment Module (`forge/env/`)

### Data Validation (Offline SFT)

```python
from forge.env import EnvHub
import forge.env.game  # triggers registration

# Create data validator for GAME environment
validator = EnvHub.make_data("GAME")

# Validate a training record
record = {
    "messages": [
        {"role": "system", "content": "You are playing chess."},
        {"role": "user", "content": "Your move as white."},
        {"role": "assistant", "content": "<think>I should open with e4.</think>\ne2e4"},
    ],
    "env": "GAME",
    "score": 1.0,
}

issues = validator.validate_entry(record)
if issues:
    print(f"Validation issues: {issues}")
else:
    print("Record is valid")

# Auto-clean a record (fix minor format issues)
cleaned = validator.clean_entry(record)
```

### Interactive Environment (GEM Protocol)

```python
from forge.env import EnvHub
import forge.env.game

# Create interactive GAME environment
env = EnvHub.make_gem("GAME")

# Gymnasium-style interaction loop
obs, info = env.reset(seed=42)
print(f"Initial observation: {obs.text}")

# Take an action
result = env.step("e2e4")
obs, reward, terminated, truncated, info = result.as_tuple()

print(f"Reward: {reward}, Done: {terminated}")
env.close()
```

### Sandbox Lifecycle

```python
from forge.env import Sandbox, SandboxConfig

# Configure a sandbox for code execution
config = SandboxConfig(
    image="python:3.11",
    memory="16g",
    cpus=4,
    timeout=300,
)

sandbox = Sandbox(config)
await sandbox.start()

# Execute commands in the sandbox
result = await sandbox.execute("python -c 'print(42)'")
print(f"stdout: {result.stdout}, exit_code: {result.exit_code}")

await sandbox.stop()
```

### Registry Operations

```python
from forge.env import EnvRegistry, EnvHub
import forge.env.game
import forge.env.navworld

# List all registered environments
print(EnvRegistry.list_envs())       # Data validators
print(EnvHub.list_all())             # All (data + GEM)
print(EnvHub.has_gem("NAVWORLD"))    # Check GEM availability

# Get environment by name
validator = EnvRegistry.make("GAME")
```

---

## Layer 0: Prompt Engine (`forge/prompt/`)

### Building Messages

```python
from forge.prompt.builder import PromptBuilder

# Build prompt for GAME environment
pb = PromptBuilder("game")
messages = (
    pb.system("system", game_name="chess")
      .user("You are playing as white. The board is in starting position.")
      .build()
)

# messages is a list of OpenAI-format dicts:
# [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
```

### Loading Tool Schemas

```python
from forge.prompt.tools import load_tools, tool_names, get_tool_schema

# Load all tools for NAVWORLD
tools = load_tools("navworld")

# Get available tool names
names = tool_names("navworld")  # e.g., ["search_poi", "get_route", ...]

# Get specific tool schema
schema = get_tool_schema("navworld", "search_poi")
```

---

## Layer 0: Training Backend (`forge/training/`)

### Creating a Training Configuration

```python
from forge.training.config import SwiftConfig, TrainType, TunerType

# LoRA SFT (default, most common)
config = SwiftConfig(
    model="Qwen/Qwen3-32B",
    train_type="sft",
    tuner_type="lora",
    lora_rank=64,
    lora_alpha=128,
    learning_rate=1e-4,
    max_length=8192,
    per_device_train_batch_size=2,
    gradient_accumulation_steps=8,
    deepspeed="zero2",
    num_gpus=4,
)

# Full parameter SFT (requires DeepSpeed ZeRO-3)
full_config = SwiftConfig(
    model="Qwen/Qwen3-32B",
    train_type="sft",
    tuner_type="full",
    quant_method=None,
    quant_bits=None,
    learning_rate=5e-5,
    max_length=32768,
    deepspeed="zero3",
    num_gpus=8,
)

# DPO RLHF
dpo_config = SwiftConfig(
    train_type="rlhf",
    rlhf_type="dpo",
    tuner_type="lora",
    beta=0.1,
)

# GRPO RLHF
grpo_config = SwiftConfig(
    train_type="rlhf",
    rlhf_type="grpo",
    tuner_type="lora",
    num_generations=8,
    max_completion_length=512,
)
```

### Generating Training Scripts

```python
from forge.training.sft import SwiftBackend

backend = SwiftBackend()

# Validate configuration
issues = backend.validate_config(config)
if issues:
    print(f"Config issues: {issues}")

# Generate ms-swift YAML config
yaml_dict = config.to_yaml_dict(dataset_path="/data/train.jsonl")

# Generate training script
script = backend.generate_script(config, dataset_path="/data/train.jsonl")
```

### Model Management

```python
from forge.training.model import merge_lora_adapter, get_hf_latest_revision

# Merge LoRA adapter into base model
merge_lora_adapter(
    base_model="Qwen/Qwen3-32B",
    adapter_path="/root/checkpoints/checkpoint-300",
    output_path="/root/merged_model",
)

# Get latest revision from HF
revision = get_hf_latest_revision("monokoco/affine-model")
```

---

## Layer 1: Data Pipeline (`forge/pipeline/`)

### Data Ingestion

```python
from forge.pipeline.data import DataPipeline
import forge.env.navworld

pipeline = DataPipeline()

# Ingest records with automatic validation and dedup
records = [
    {"messages": [...], "env": "NAVWORLD", "score": 0.8},
    {"messages": [...], "env": "NAVWORLD", "score": 0.6},
]

report = pipeline.ingest(records, env="NAVWORLD")
print(f"Accepted: {report.accepted}")
print(f"Rejected: {report.rejected}")
print(f"Duplicated: {report.duplicated}")
```

### Evaluation

```python
from forge.pipeline.eval import Evaluator

evaluator = Evaluator()

report = evaluator.evaluate(
    model="monokoco/affine-v2.27",
    envs=["GAME", "NAVWORLD", "LIVEWEB", "SWE-SYNTH"],
    samples=100,
)

for env_result in report.env_results:
    print(f"{env_result.env}: {env_result.score:.2f}")

print(f"Geometric mean: {report.geo_mean:.2f}")
```

### Experiment Tracking

```python
from forge.pipeline.experiment import ExperimentTracker

tracker = ExperimentTracker(experiments_dir="experiments/")

# Create new experiment
exp = tracker.create({
    "version": "v2.28",
    "variable": "Add LGC-v2 data",
    "hypothesis": "Adding LGC data should improve L5 coverage",
    "data_mix": {"GAME": 10000, "NAVWORLD": 4300, "LGC": 500},
    "config": {"train_type": "sft", "tuner_type": "full", "deepspeed": "zero3"},
})

# Update status
tracker.update_status("v2.28", "running")

# Record results
tracker.record_results("v2.28", {
    "GAME": 35.0,
    "NAVWORLD": 42.0,
    "LGC": 15.0,
    "cost_usd": 9,
})
```

---

## Layer 2: Agent Loop (`forge/agent/`)

### Running the Evolution Loop

```python
from forge.agent.loop import EvolutionLoop
from forge.agent.strategist import StrategistAgent
from forge.agent.trainer import TrainerAgent
from forge.agent.data_agent import DataAgent

# Initialize agents
strategist = StrategistAgent()
trainer = TrainerAgent()
data_agent = DataAgent()

# Create evolution loop
loop = EvolutionLoop(
    strategist=strategist,
    trainer=trainer,
    data_agent=data_agent,
)

# Run one iteration
result = loop.step()
print(f"Step result: {result.status}")
print(f"Actions taken: {result.actions}")
```

### Gap Analysis

```python
from forge.agent.strategist import StrategistAgent

strategist = StrategistAgent()

# Analyze competitive gaps
analysis = strategist.analyze_gaps()
print(f"Weakest environment: {analysis.weakest_env}")
print(f"Suggested action: {analysis.recommendation}")
```

---

## CLI Examples

### Complete Training Workflow

```bash
# 1. Check leaderboard position
python3 -m forge score --top 10

# 2. Validate data quality
forge data audit
forge data validate data/canonical/game.jsonl --env GAME

# 3. Prepare and launch SFT training (LoRA)
forge train launch combined_sft.jsonl \
  --dataset-repo monokoco/affine-sft-data \
  --lr 1e-4 --lora-r 64 --max-length 8192 \
  --batch-size 2 --grad-accum 8 \
  --gpu H200

# 4. Or launch Full SFT with DeepSpeed ZeRO-3
forge train launch combined_sft.jsonl \
  --dataset-repo monokoco/affine-sft-data \
  --tuner-type full --no-quant \
  --deepspeed zero3 \
  --lr 5e-5 --max-length 32768 \
  --gpu H200

# 5. Monitor training
forge rental status

# 6. Deploy model for evaluation
forge rental start-sglang monokoco/affine-v2.27 --tp 4

# 7. Run multi-environment evaluation
forge rental start-eval monokoco/affine-v2.27 \
  --envs GAME,NAVWORLD,LIVEWEB,SWE-SYNTH \
  --samples 100

# 8. Check results
forge score --top 10
```

### RLHF Training Workflow

```bash
# 1. Prepare DPO preference data
# (requires paired chosen/rejected examples)

# 2. Launch DPO training
forge train launch dpo_data.jsonl \
  --dataset-repo monokoco/affine-dpo-data \
  --train-type rlhf --rlhf-type dpo \
  --sft-adapter monokoco/affine-v2.27-lora

# 3. Or use the RLHF shortcut
forge train rlhf-launch dpo_data.jsonl \
  --dataset-repo monokoco/affine-dpo-data \
  --rlhf-type grpo \
  --sft-adapter monokoco/affine-v2.27-lora
```

### Data Management Workflow

```bash
# Audit all canonical data
forge data audit

# Ingest new data (validate + dedup + store)
forge data ingest new_game_data.jsonl --env GAME --source bot_v3

# Analyze dataset statistics
forge data analyze data/canonical/game.jsonl

# Upload to HuggingFace
forge data canonical-upload --env all

# Generate NAVWORLD data
forge data navworld-gen -n 50 --type half_day
forge data navworld-gen -n 50 --phase1
```
