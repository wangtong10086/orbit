# Affine System Complete Guide

## I. What is Affine

Affine is **Subnet 120** on Bittensor, an incentive-based RL (reinforcement learning) training network. Core mechanism:

- **Miners**: Download the current best model → improve via RL/SFT training → deploy the improved model to Chutes (GPU inference platform)
- **Validators**: Sample and score miner models across multiple evaluation environments → compute rankings → set on-chain weights
- **Incentives**: Higher ranking = more TAO rewards, using a **winner-takes-all** mechanism

**Our goal**: As a miner, train a model with the highest overall score across all environments, achieve leaderboard #1.

---

## II. Leaderboard Scoring Mechanism (4-Stage Algorithm)

### Stage 1: Data Collection
- Retrieve each miner's sampling scores per environment from the DynamoDB `sample_results` table
- Calculate average score per environment
- Verify completeness: sample count / total tasks ≥ environment threshold (0.8~0.9)
- Environments not meeting the threshold don't count toward that miner's score

### Stage 2: Pareto Anti-Copying Filter
- Detect model copying: if miner B's scores cannot exceed miner A on any environment subset, and A registered earlier
- Then B is considered a potential copy of A and gets filtered out
- Threshold formula: `threshold = 0.2 + 0.8 * A's score`, also adjusted by z-score based on sample size
- **Key**: Earlier-registered miners have a natural advantage; newcomers must clearly exceed on scores

### Stage 3: Subset Scoring
- Create environment subset combinations (L1=single env, L2=two env combos...)
- Use **geometric mean** within each subset for composite score
- Layer weights grow exponentially: `weight = n * base^(layer-1)`, base=2
- Rank within each subset, distribute weights by rank (with decay factor 0.5)

### Stage 4: Weight Normalization
- Accumulate all subset contributions
- Apply minimum weight threshold (1%), below-threshold weight goes to UID 0
- Normalize all weights to sum to 1.0
- Results written on-chain

### Currently Active Environments

| Env | Scheduling Weight | Samples | Completeness Threshold | Description |
|-----|-------------------|---------|----------------------|-------------|
| **GAME** | 3.0 | ~200 | 0.8 | OpenSpiel strategy games (**highest weight, top priority**) |
| PRINT | 1.0 | ~200 | 0.9 | Program synthesis (print output reasoning) |
| LGC-v2 | 1.0 | ~250 | 0.9 | Logic reasoning games |
| SWE-SYNTH | 1.0 | ~100 | 0.8 | Software engineering bug fixing |
| LIVEWEB | 1.0 | ~200 | 0.8 | Browser agent web navigation |
| NAVWORLD | 1.0 | ~100 | 0.8 | Travel planning (tool use, recently updated to standard tool calling, so most old samples cannot be used directly) |
| LOGPROBS | 1.0 | ~20 | 0.9 | Log probability evaluation (sampling only, not scored) |

---

## II.5. Training Constraints & Strategy

### Model Constraints
- **Must use Qwen3-32B** as base architecture
- Can start training from `Qwen/Qwen3-32B` base model
- Can also do secondary training on top leaderboard model (if that model is also Qwen3-32B architecture)
- Need to judge which path has higher ROI

### Strategy Options
1. **From base**: Higher data quality requirements, longer training time, but not limited by others' models
2. **From top model secondary training**: Higher starting point, potentially faster results, but limited by top model's capability ceiling
3. **Hybrid strategy**: First run top model for baseline, simultaneously train a stronger version from base

### GPU Machine Selection
Qwen3-32B has 32B parameters, training requirements:
- **Full fine-tuning**: At least 4×H100 80GB (~320GB VRAM), not recommended, too expensive
- **QLoRA (4-bit)**: 1×H100 80GB can run, recommended starting approach
- **LoRA (bf16)**: 2×H100 80GB, better quality but double cost
- **Recommendation**: Start with 1×H100/H200 QLoRA to verify approach, then decide whether to upgrade based on results

Targon machine type selection:
- Hopper (H100/H200) — First choice, best price-performance
- Blackwell (B200) — Stronger if available, but possibly more expensive

---

## III. Database Structure (DynamoDB)

### Connection Information
- Service: AWS DynamoDB
- Region: `us-east-1` (default, configured via `AWS_REGION` env var)
- Table prefix: `affine` (configured via `DYNAMODB_TABLE_PREFIX`)
- API address: `https://api.affine.io/api/v1`

### Core Tables

#### `affine_sample_results` — Sampling Results (SFT Data Source)
```
PK: MINER#{hotkey}#REV#{revision}#ENV#{env}
SK: TASK#{task_id}

Fields:
- miner_hotkey: Miner hot key
- model_revision: Model version hash
- model: Model name (HuggingFace repo)
- env: Environment name
- task_id: Task ID (integer)
- score: Score (float)
- latency_ms: Latency (milliseconds)
- extra_compressed: gzip-compressed JSON (contains conversation data! This is the key data for SFT)
- timestamp: Timestamp (milliseconds)
- validator_hotkey: Validator hot key
- block_number: Block number
- signature: Signature
- ttl: 30-day auto-expiration

GSI: timestamp-index (gsi_partition='SAMPLE', timestamp sorted)
```

**extra_compressed decompressed contains**:
```json
{
  "conversation": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ],
  "request": { ... },
  "response": "..."
}
```
This is the core source for SFT training data.

#### `affine_miners` — Miner Information
```
PK: UID#{uid}
GSI: is-valid-index (is_valid='true')
GSI: hotkey-index (hotkey)

Fields: hotkey, revision, model, is_valid, uid, first_block, etc.
```

#### `affine_scores` — Score Snapshots
```
PK: SCORE#{block_number}
SK: MINER#{hotkey}
GSI: latest-block-index

Fields: uid, overall_score, scores_by_env, scores_by_layer, etc.
```

#### Other Tables
- `affine_task_pool`: Pending evaluation task queue
- `affine_score_snapshots`: Score metadata
- `affine_miner_stats`: Historical statistics
- `affine_anti_copy_results`: Anti-copying detection results
- `affine_system_config`: System configuration (environment config, etc.)
- `affine_execution_logs`: Execution logs

### API Endpoints (No AWS credentials required)
```
GET /scores/latest?top=256         → Latest leaderboard
GET /config/environments           → Environment configuration
GET /samples/scoring?range_type=scoring → Raw scoring data
GET /scores/weights/latest         → Latest weights
```

---

## IV. What is Affinetes

Affinetes is Affine's **lightweight container orchestration framework**, used for packaging and running evaluation environments.

### Core Concept
Environment developers only need to write an `env.py` (defining an Actor class); Affinetes automatically handles:
- Docker container building and management
- HTTP API injection (no need to write a web server)
- Multi-instance load balancing
- SSH remote deployment
- Health checks and auto-restart

### Usage
```python
from affinetes import load_env

# Load environment (automatically starts Docker container)
env = await load_env(
    image="affine-game:latest",
    mode="docker",         # docker | url | basilica
    replicas=3,
    mem_limit="8g",
    env_vars={"API_KEY": "..."},
)

# Call evaluation
result = await env.evaluate(
    task_id=42,
    model="deepseek-ai/DeepSeek-V3",
    base_url="https://llm.chutes.ai/v1",
    temperature=0.0,
)
# result = {"score": 0.85, "success": True, "extra": {"conversation": [...]}}
```

### Evaluation Environment Interface
Each environment implements two interfaces:

**Traditional evaluation** (one-shot):
```python
class Actor:
    async def evaluate(self, task_id, model, base_url, temperature, api_key, **kwargs):
        # Execute evaluation, return score, success, extra
```

**OpenEnv training interface** (interactive, for RL):
```python
class Actor:
    async def reset(self, task_id, seed):  # Initialize environment
    async def step(self, action):           # Execute action, return obs, reward, done
    async def stop(self, episode_id):       # End
```

### Key Environment Implementations

**GAME (OpenSpiel)**: `affinetes/environments/openspiel/`
- Strategy games (Go, Chess and other strategy games)
- Scheduling weight 3.0, highest priority

**LIVEWEB**: Separate project `liveweb-arena/`
- Playwright-driven browser agent
- 34 templates, 5 plugins (Stooq stocks, CoinGecko crypto, Taostats blockchain, Hybrid cross-site)
- Real-time web interaction, ground truth from API data collection
- ~65 million task combinations
- `env.py` implements OpenEnv interface (reset/step)

**Others**:
- PRINT: Program synthesis, `affinetes/environments/affine/`
- LGC-v2: Logic reasoning, `affinetes/environments/primeintellect/lgc-v2/`
- SWE-SYNTH: Bug fixing, `affinetes/environments/SWE-SYNTH/`
- NAVWORLD: Travel planning (Chinese), `affinetes/environments/qqr/`

### CLI Tools
```bash
afs init my-env --template actor    # Initialize environment
afs build environments/my-env       # Build Docker image
afs run my-env:v1 --name my-env     # Start container
afs call my-env evaluate --arg task_id=10  # Call method
afs validate environments/my-env    # Validate seed consistency
```

---

## V. What is Targon

Targon is a **confidential decentralized AI cloud** on Bittensor (Subnet 4), providing GPU/CPU compute.

### Relationship to Us
We need GPUs to train models; Targon provides rentable GPU machines (CVM - Confidential Virtual Machines).

### Hardware Types
| Type | CPU | GPU | Storage |
|------|-----|-----|---------|
| CPU | AMD EPYC 9xx4 (SEV-SNP) | None | 1TB+ |
| Hopper | Intel Xeon 6 (TDX) | H100/H200 | 3TB+ |
| Blackwell | Intel Xeon 6 (TDX) | B200 | 3TB+ |

### How to Use

**1. Acquire a Machine**
Through Targon's auction mechanism to obtain CVM instances. Machine info via API:
```
GET https://tower.targon.com/api/v1/auctions
```

**2. SSH Connection**
```bash
ssh root@<cvm_ip>
# CVM listens on port 8080 by default for API
```

**3. CLI Tools**
```bash
# Install (requires Go environment)
cd targon && just install-cli

# Main commands
targon-cli attest --uid 123              # GPU verification
targon-cli get nodes --uid 123           # Get node info
targon-cli vali containers --ip <ip>     # View containers
targon-cli vali logs --ip <ip> --container <name>  # View logs
```

**4. Authentication: Epistula Signing**
All API requests use Substrate key signing:
```
Headers:
- Epistula-Request-Signature
- Epistula-Timestamp
- Epistula-Uuid
- Epistula-Signed-For
- Epistula-Signed-By
```

### Key Issues & Solutions

#### Issue 1: Machines Are Extremely Unstable
CVMs may disconnect at any time, and **data cannot be recovered**.

**Solution**:
- Auto-backup checkpoints to local every 30 minutes
- Sync critical checkpoints to HuggingFace Hub
- Wrap training process with `screen` or `tmux`
- Set `save_steps=100` in training script for frequent saves
- Tool: `./forge remote backup <host>`

#### Issue 2: SSH Connection Inconvenient
Need to manually SSH connect each time, low efficiency.

**Solution**:
Our `remote_manager.py` provides local remote operations without interactive SSH:
```bash
./forge remote exec gpu1 "nvidia-smi"           # Remote execution
./forge remote upload gpu1 data.jsonl /root/     # Upload file
./forge remote download gpu1 /root/ckpt ./       # Download file
./forge remote watch gpu1                        # Real-time log monitoring
./forge remote status                            # Batch health check
```

#### Issue 3: Environment Configuration Lost
All environments need reinstallation after machine rebuild.

**Solution**:
One-click environment setup: `./forge remote setup <host>`
Automatically installs PyTorch, Transformers, PEFT, TRL, and other training dependencies.

#### Issue 4: Training Progress Not Visible
Training runs remotely, cannot see progress locally.

**Solution**:
```bash
./forge remote watch gpu1                # tail -f remote logs
./forge train monitor gpu1               # Structured status report (GPU/disk/checkpoint)
```

### Machine Configuration File
Register machines in `affine-forge/machines.json`:
```json
{
  "machines": [
    {
      "name": "gpu1",
      "host": "192.168.1.100",
      "port": 22,
      "user": "root",
      "key": "~/.ssh/id_rsa"
    }
  ]
}
```
Add machine: `./forge remote add gpu1 192.168.1.100 --port 22 --user root`

---

## VI. SFT Data Extraction Flow

### Data Source
The `extra_compressed` field in the DynamoDB `sample_results` table contains complete conversation data.

### Extraction Flow
```bash
# 1. View available environments and statistics
./forge envs
./forge stats

# 2. Extract high-score samples (score >= 0.5)
./forge data --env GAME --min-score 0.5 -o data/game_sft.jsonl

# 3. Extract data from specific miner
./forge data --env GAME --min-score 0.5 --hotkey 5H1YrQ -o data/game_top1.jsonl
```

### SFT Data Format (Output JSONL)
```json
{
  "messages": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ],
  "score": 0.85,
  "env": "GAME",
  "task_id": 42
}
```

### Notes
- Different environments may have different `extra` formats; `data_pipeline.py` attempts multiple parsing methods
- Prioritize GAME environment data extraction (3x weight)
- Use only high-score samples (score filter); low-score samples pollute training
- Database data has 30-day TTL auto-expiration; need to extract new data periodically

---

## VII. Complete Training Pipeline

```
Observe leaderboard → Determine target environments → Extract high-score data → Prepare SFT dataset
    ↓                                                                          ↓
Evaluate new model ← Deploy to Chutes ← Backup checkpoint ← Remote training
    ↓
Update strategy, return to first step
```

### One-Click Execution
```bash
./forge train full GAME gpu1 --min-score 0.5
```
Automatically completes: data extraction → dataset upload → generate training script → start training

### Default Training Configuration
- Base model: `unsloth/Qwen3-32B-bnb-4bit` (pre-quantized, 18GB)
- Method: QLoRA (4-bit NF4 + LoRA r=64, alpha=128)
- Sequence length: 4096
- Batch: 2 × 8 gradient accumulation = effective 16
- Learning rate: 1e-4, warmup 3%
- Epochs: 1
- Packing: True
- Save interval: every 100 steps

See `knowledge/training.md` for hyperparameter evolution and lessons.

---

## VIII. Key File Path Index

```
./                                              # Project workspace root
├── ../affine-cortex/                           # Affine core code (reference)
│   ├── affine/database/                        # DynamoDB data access layer
│   │   ├── client.py                           # DB connection management
│   │   ├── schema.py                           # Table structure definitions
│   │   ├── base_dao.py                         # Base DAO (serialization/compression)
│   │   └── dao/sample_results.py               # Sample results queries
│   ├── affine/src/scorer/                      # 4-stage scoring algorithm
│   │   ├── scorer.py                           # Main orchestrator
│   │   ├── stage1_collector.py                 # Data collection
│   │   ├── stage2_pareto.py                    # Pareto filtering
│   │   ├── stage3_subset.py                    # Subset scoring
│   │   └── stage4_weights.py                   # Weight normalization
│   ├── affine/src/miner/rank.py                # Ranking display
│   └── affine/utils/api_client.py              # API client
│
├── ../affinetes/                               # Container orchestration framework (reference)
│   ├── affinetes/api.py                        # SDK entry
│   ├── affinetes/cli/commands.py               # CLI commands
│   └── environments/                           # All evaluation environments
│       ├── openspiel/                          # GAME environment
│       ├── affine/                             # PRINT environment
│       ├── primeintellect/lgc-v2/              # LGC-v2 environment
│       ├── SWE-SYNTH/                          # SWE-SYNTH environment
│       └── qqr/                                # NAVWORLD environment
│
├── ../liveweb-arena/                           # LIVEWEB environment (separate project)
│   ├── env.py                                  # OpenEnv interface
│   ├── eval.py                                 # Standalone evaluation entry
│   └── liveweb_arena/
│       ├── core/                               # Core logic
│       └── plugins/                            # 5 website plugins
│
├── ../targon/                                  # GPU cloud documentation (reference)
│   ├── docs/miner/miner.md                    # Miner configuration
│   ├── docs/validator/validator.md             # Validator configuration
│   └── targon/cmd/targon-cli/main.go           # CLI tool source
│
└── ./                                          # affine-swarm (this repository)
    ├── CLAUDE.md                               # Universal rules + documentation map
    ├── PLAYBOOK.md                             # Strategy + priorities
    ├── STATUS.md                               # Active work tracking
    ├── forge/                                  # Python CLI package
    ├── scripts/                                # Standalone scripts
    ├── prompts/                                # Agent prompts (loop_main.md, data_synth.md)
    ├── experiments/                            # Experiment YAML + results.tsv
    ├── knowledge/                              # Accumulated learnings
    └── docs/affine-system.md                   # This document
```
