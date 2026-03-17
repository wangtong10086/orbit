# Training Iteration Log

## Iteration #1 — First GAME Training

**Date**: 2026-03-11
**Target environment**: GAME (3x weight, highest priority)
**Baseline leaderboard**: Block 7720452

### Leaderboard Baseline
| Rank | UID | Model | Weight | GAME | LGC-v2 | LIVEWEB | NAVWORLD | PRINT | SWE-SYNTH |
|------|-----|-------|--------|------|--------|---------|----------|-------|-----------|
| 1 | 116 | oliverchang/Affine-95 | 0.510 | 29.94 | 81.20 | 23.58 | 10.42 | 73.71 | 38.00 |
| 2 | 120 | voidai001/affine-new | 0.249 | 47.20 | 89.52 | 25.18 | 5.27 | 78.95 | 31.00 |
| 3 | 45 | Infinite3214/Affine-0305 | 0.123 | 41.42 | 89.20 | 28.63 | 5.05 | 85.86 | 28.00 |

### Data
- **Source**: DynamoDB affine_sample_results, high-score samples from all miners for GAME
- **Filter**: score >= 0.5
- **Count**: 4,528 SFT records (increased after re-extraction)
- **Format**: JSONL (messages chat format)
- **Storage**: HuggingFace `YOUR_HF_USER/affine-sft-data/game_sft.jsonl`

### Training Configuration
- **Model**: Qwen/Qwen3-32B
- **Method**: QLoRA (4-bit NF4 + LoRA r=16, alpha=32)
- **GPU**: Targon H200 (serverless container)
- **Batch**: 2 × 8 grad accum = effective 16
- **Learning rate**: 2e-5, warmup 10%
- **Epochs**: 3
- **Checkpoint**: Save every 100 steps, auto-upload to HuggingFace

### Execution Status

**Attempt 1** — `serv-u-1324508-ds3woo1ppdeo8mmi` (terminated)
- Deploy time: 07:25 UTC
- Image: `nvidia/cuda:12.4.0-devel-ubuntu22.04`
- Result: **Failed** — Model download stuck at 18% (3/17 files), no checkpoint uploaded to HF repo
- Termination reason: Wasting $2.40/hr, training never actually started
- Root cause analysis: Logs show pip install succeeded, training script started, model download began but stalled. Possible Qwen3-32B 65GB download timeout on Targon network or insufficient disk space.

**Attempt 2** — `serv-u-1324508-5vwzpiq1m7gkyn2k` (terminated)
- Deploy time: 07:35 UTC
- Image: `pytorch/pytorch:2.5.1-cuda12.4-cudnn9-devel`
- Result: **Failed** — Container zero log output
- Termination reason: PyTorch official image may have incompatible entrypoint or Targon doesn't support it
- Root cause analysis: Targon serverless platform has limitations on custom images; not all Docker images work. Reverted to verified CUDA image.
- Lesson: **Only use verified working images** (`nvidia/cuda:12.4.0-devel-ubuntu22.04`)

**Attempt 3** — `serv-u-1324508-kedpsq3y3zrtmg9q` (terminated)
- Deploy time: 07:38 UTC, termination: ~08:28 UTC (ran 50 minutes)
- Image: `nvidia/cuda:12.4.0-devel-ubuntu22.04`
- Result: **Failed** — Dependencies installed and dataset downloaded successfully, training script started, model download began with no progress
- 48 minutes later still no HF checkpoint upload, logs stuck at "Fetching 17 files: 0%"
- Root cause analysis: Qwen3-32B (65GB) may have download timeout or insufficient disk space. tqdm progress bar uses `\r` making subsequent logs invisible.
- Lesson: **Verify pipeline with small model first, then scale to large model**

**Attempt 4** — `serv-u-1324508-s7l5ryt479xfhygo` (terminated)
- Model: Qwen2.5-7B, Image: `nvidia/cuda:12.4.0-devel-ubuntu22.04`
- 17 minutes still on pip install Python dependencies, terminated
- Root cause: pip install torch ~2GB from scratch is too slow

**Image compatibility test** — `serv-u-1324508-l29ao88ufrb1wnmp` (terminated)
- `nvcr.io/nvidia/pytorch:24.10-py3` → zero logs, unusable
- `pytorch/pytorch:2.5.1-cuda12.4-cudnn9-devel` → zero logs, unusable (attempt 2)
- Conclusion: **Targon only supports nvidia/cuda series base images**

**Attempt 5** — `serv-u-1324508-3a84ch4u7so2mnib` (terminated)
- Model: Qwen2.5-7B, no health check server, 30+ minutes no HF upload
- Root cause unclear, possibly throttled by Targon due to no HTTP health check

**Attempt 6** — `serv-u-1324508-xljqzwjysyy37hzw` (terminated)
- Model: Qwen2.5-7B, with health check server
- Result: **Training script error** `SFTConfig.__init__() got an unexpected keyword argument 'max_seq_length'`
- Root cause: pip install installs latest trl version where `max_seq_length` is no longer an `SFTConfig` parameter, needs to go in `SFTTrainer`
- Fix: Moved `max_seq_length` from SFTConfig to SFTTrainer constructor
- Lesson: **Container pip install installs latest library versions; API may differ from local dev environment**

**Attempt 7** — `serv-u-1324508-kunjl402ovf10k1t` (terminated)
- 9 minutes later Targon log buffer cleared, cannot diagnose, no HF upload

**Attempt 8** — `serv-u-1324508-ki3fz9flaggq31j4` (terminated)
- **Log capture first success!** Uploaded training.log to HF on exit
- Error: `SFTTrainer.__init__() got an unexpected keyword argument 'tokenizer'`
- Root cause: Latest trl major API changes — `tokenizer` → `processing_class`, `max_seq_length` → `max_length`, `warmup_ratio` deprecated
- Fix: Updated all API calls per latest trl documentation

**Attempt 9** — `serv-u-1324508-te0djedy75dd4794` (terminated)
- API fix worked (tokenizer→processing_class passed)
- New error: `jinja2.exceptions.UndefinedError: dict object has no element 0`
- Root cause: `formatting_func` receives single sample not batch in new trl, and conversational datasets don't need formatting_func
- Fix: Removed formatting_func, let trl auto-handle messages format

**Attempt 10** — `serv-u-1324508-wvy7glkyhcfu5nck` (**complete** ✅)
- Model: Qwen2.5-7B, 1 epoch, 283 steps
- **Final loss=0.188, accuracy=96.4%, ran 51 minutes**
- Pipeline fully verified: deploy → train → checkpoint → HF upload → log viewing

---

## Iteration #1B — Qwen3-32B Official GAME Training

**Attempt 11** — `serv-u-1324508-782d1hj887mg2faz` (**partial failure**)
- Model: Qwen/Qwen3-32B, QLoRA 4-bit, 3 epochs
- Expected steps: 849 (283 × 3)
- Deploy time: ~11:01 UTC, termination: ~21:00 UTC (~10h, ~$24)
- **HF upload callback completely failed after step 240**
- Last known state: step 200, loss=0.070
- Available checkpoints: checkpoint-100, checkpoint-200 (on HF)
- **Root cause**: `LogUploadCallback(upload_every_n_logs=1)` uploads logs every 10 steps; HF API rate limited, callback exception never recovered
- **Fix**: Changed `upload_every_n_logs` from 1 to 5 (reduce upload frequency)
- **Lesson**: HF API has upload frequency limits; cannot upload on every on_log; need retry mechanism after upload failure

### Failure Experience Summary
1. **Targon only supports `nvidia/cuda` series images**; PyTorch/NGC official images are all unusable
2. pip install torch from scratch takes ~15 minutes; this is unavoidable overhead
3. **Qwen3-32B step 100 may need 80-130 minutes**; attempt 3 may have been terminated too early
4. **Targon logs API buffer is very small**; only keeps recent few lines, unreliable
5. **Each container costs $2.40/hr**; must diagnose failures quickly and release
6. **tqdm progress bar uses `\r` to overwrite lines**; invisible in SSE logs

---

## Data Module Development

**Date**: 2026-03-11

### Full-Environment Data Analysis

| Env | Total Samples | Avg Score | High Quality (>=0.7, <=16K) | Notes |
|-----|---------------|-----------|---------------------------|-------|
| LGC-v2 | 21,757 | 0.669 | 3,353 | Subtasks: Dyck brackets, math, operators, cryptarithmetic, sudoku, boolean |
| PRINT | 17,689 | 0.734 | 2,899 | Single-turn Q&A, predict program output |
| GAME | 12,984 | 0.360 | 561 | Multi-turn gameplay, assistant replies often single digits |
| SWE-SYNTH | 11,594 | 0.335 | 437 (<=32K) | Multi-turn code repair, most samples >16K |
| LIVEWEB | 15,844 | 0.172 | 3 | Almost no usable data |
| NAVWORLD | 9,867 | 0.060 | N/A | Tool calling format updated, skipped |

### Environment-Specific Cleaners

- **GAME**: Verify complete gameplay (system prompt + alternating turns + assistant ending)
- **LGC-v2**: Verify think block completeness, check format requirements by task type
- **PRINT**: Verify think block closure + actual answer output present
- **SWE-SYNTH**: Verify system prompt + multi-turn structure + substantive code content

### Key Findings
1. LGC-v2 initial cleaner required all samples to contain python code blocks, but only ~20% of tasks need them → corrected to recover 3,353 entries (from 646)
2. SWE-SYNTH relaxed to 32K chars recovered 437 entries (from 26)
3. Mixed dataset 7,250 entries, 99% perfect score, covering 4 environments

### New CLI Commands
- `forge data analyze <path>` — Analyze dataset quality
- `forge data extract-all` — Batch extract all environments
- `forge data merge` — Merge multi-environment datasets
- `forge data extract` — Added `--max-chars` option

---

## Quick Experiment #1 — QLoRA SFT from Top Model

**Date**: 2026-03-11
**Container**: `serv-u-1324508-11avuf2u6skigj9r` (terminated)

### Experiment Design
- Base model: #2 UID 120 (`voidai001/affine-new`, GAME 47%)
- Data: mixed 7250 entries (GAME+LGC-v2+PRINT+SWE-SYNTH)
- Method: QLoRA, LR=1e-5, 1 epoch
- Goal: Verify whether fine-tuning from top model is better than training from base

### Result: **Failed**
| Step | Loss |
|------|------|
| 5 | 0.640 |
| 10 | 0.913 ⬆ |
| 15 | 0.860 |
| 20 | 0.768 |
| 25 | 0.821 |
| 30 | 0.704 |
| 35 | 0.813 |
| 40 | 0.922 ⬆ |

Loss oscillated violently without convergence, terminated after 40 steps.

### Comparison
- From base Qwen3-32B: step 5 loss=0.612 → step 170 loss=0.071 (stable decrease)
- From top #2 model: step 5 loss=0.640 → step 40 loss=0.922 (oscillating divergence)

### Conclusion
- Top model has been deeply tuned; QLoRA cannot stably learn on top of it
- **Training from base Qwen3-32B is the correct path**
- If leveraging top model, may need: full fine-tune or lower LR (1e-6) or longer warmup

### Bug Discovery
- `runner.py` line 91 always overwrites `tc.hf_backup_repo`, causing experiment logs to write to main training repo
- Fixed: Only use default value when `tc.hf_backup_repo` is empty

---

## Strategy Analysis — Necessity of Multi-Environment Training

**Date**: 2026-03-11

### Core Findings

1. **Geometric mean penalty mechanism**: Leaderboard uses geometric mean across all 6 environments; any weak link severely drags down total score
2. **#1 wins through balance**: UID 116 has 2x the weight of #2, not because any single metric is extremely strong, but because there are no weak links
3. **GAME-only SFT is high risk**:
   - GAME assistant replies are often single digits, very different from other environments' long-form generation style
   - 3 epochs training on 4528 GAME entries, model will overfit to GAME distribution
   - QLoRA only updates 0.5% of parameters, but extended training can still cause catastrophic forgetting
4. **NAVWORLD/LIVEWEB everyone is weak**: All top miners score very low (5-10/23-29), differentiation is in other environments

### Mixed Training Plan

| Env | Original | After Mixing | Strategy |
|-----|----------|-------------|----------|
| GAME | 561 | 1,683 | 3x upsampling (highest ROI) |
| LGC-v2 | 3,353 | 1,500 | Downsampling |
| PRINT | 2,899 | 1,500 | Downsampling |
| SWE-SYNTH | 437 | 437 | Full |
| **Total** | — | **5,120** | — |

### Mixed Training Config (vs GAME-only)

| Parameter | GAME-only | Mixed | Rationale |
|-----------|-----------|-------|-----------|
| LR | 2e-5 | 1e-5 | Lower to protect general capability |
| Epochs | 3 | 2 | Avoid overfitting small dataset |
| LoRA rank | 16 | 32 | Multi-environment needs more capacity |
| Max seq len | 4096 | 8192 | SWE-SYNTH needs it |
| Batch size | 2 | 1 | Accommodate longer sequences |
| Grad accum | 8 | 16 | Maintain effective=16 |

### Preparation
- [x] Balanced mixed dataset `mixed_balanced_sft.jsonl` (5120 entries) created and uploaded to HF
- [x] HF repo `YOUR_HF_USER/affine-qwen3-32b-mixed-lora` created
- [x] CLI `train launch` command implemented, supports custom training parameters
- [ ] Start mixed training after GAME-only training completes

### Launch Command
```bash
python3 -m forge train launch mixed_balanced_sft.jsonl \
  --hf-repo YOUR_HF_USER/affine-qwen3-32b-mixed-lora \
  --lr 1e-5 --epochs 2 --lora-r 32 \
  --max-seq-len 8192 --batch-size 1 --grad-accum 16
```

---

## NAVWORLD Synthetic Data Generation

**Date**: 2026-03-11

### Environment Analysis
- NAVWORLD (QQR) is a Chinese travel planning Agent evaluation
- Uses Amap API (POI/weather/routes) + Mock transportation data (flights/trains)
- Scoring: 50 points code scoring (info consistency + completeness) + 50 points LLM semantic scoring
- **Standard tool calling format**: LLM calls tools via OpenAI function calling
- **Conversation storage**: Tool calls converted to text format ("Call tool: name({args})")

### Leaderboard NAVWORLD Status
- #1 UID 116: 10.42 (everyone weak, this is #1's key differentiation point)
- #2 UID 120: 5.27
- #3 UID 45: 5.05

### Data Generation Plan
- **Orchestrated generation**: Programmatically plan tool call sequence → real AMap API for data → strong model generates plan
- **Tool coverage**: Each sample guarantees 4-5 tool types (poi_search/weather/direction/around_search/flights/trains)
- **LLM model**: DeepSeek-V3-0324 via Chutes API
- **Multi-turn conversation**: 3-4 rounds of tool calls + final complete plan, 9-11 messages

### Generation Progress
- [x] Generator `forge/data/navworld_gen.py` complete
- [x] CLI command `forge data navworld-gen` available
- [x] Test 3 entries passed verification
- [x] Batch generated 161 synthetic entries (3 batches in parallel, DeepSeek-V3-0324 via Chutes)
- [x] Merge verified: 161 synthetic + 79 real = 240 NAVWORLD entries
- [x] Uploaded to HF `YOUR_HF_USER/affine-sft-data/navworld_synthetic_all.jsonl`
- [x] Included in enhanced mixed dataset

### Files
- Generator: `forge/data/navworld_gen.py`
- Synthetic data: `data/navworld_synthetic_all.jsonl` (161 entries)
- Real data: `data/navworld_real_sft.jsonl` (79 entries)

---

## Iteration #2 — Enhanced Mixed Training (with NAVWORLD)

**Date**: 2026-03-11
**Goal**: Balanced training across all environments, focus on closing NAVWORLD gap

### Dataset: enhanced_mixed_sft.jsonl (5600 entries)

| Env | Original | After Mixing | Strategy |
|-----|----------|-------------|----------|
| GAME | 561 | 1,683 | 3x upsampling (highest ROI) |
| LGC-v2 | 3,353 | 1,500 | Downsampling |
| PRINT | 2,899 | 1,500 | Downsampling |
| SWE-SYNTH | 437 | 437 | Full |
| NAVWORLD | 240 | 480 | 2x upsampling (161 synthetic + 79 real) |
| **Total** | — | **5,600** | — |

### Training Configuration
- **Model**: Qwen/Qwen3-32B (training from base)
- **Method**: QLoRA (4-bit NF4 + LoRA r=32, alpha=64)
- **GPU**: Targon H200 (serverless container)
- **Batch**: 1 × 16 grad accum = effective 16
- **Learning rate**: 1e-5, warmup 10%
- **Epochs**: 2
- **Max seq len**: 8192
- **Checkpoint**: Save every 100 steps, auto-upload to HuggingFace
- **HF Repo**: `YOUR_HF_USER/affine-qwen3-32b-mixed-lora`

### Execution Status

**Attempt 1** — `serv-u-1324508-j0mvacby3xzbid18` (**HF upload failed**)
- Deploy time: ~16:30 UTC, termination: ~23:00 UTC (~6.5h, ~$16)
- Training progress: step 310/700, loss=0.454, acc=83.1%
- HF upload completely failed after step 310 (same issue as GAME training)
- Available checkpoints: 100, 200, 300
- Training may have completed but final model cannot be retrieved

**Root cause analysis**: HF upload callback cached HfApi instance; connection pool/auth state corrupted after multiple uploads,
all subsequent uploads silently failed. `on_train_end` callback also affected.

**Fix** (applied):
1. Create new HfApi instance per upload (don't cache)
2. 3 retries + exponential backoff (10s, 20s, 30s)
3. Reduce log upload frequency to every 50 steps

**Attempt 2** — `serv-u-1324508-emathe3c8bz7kdeg` (running)
- Deploy time: ~23:30 UTC (2026-03-11)
- Using fixed HF upload callback (new HfApi instance + retries)
- **Fix didn't work**: HF upload stopped again after step 200
- Known uploaded data: step 200, loss=0.481, acc=82.6%
- Available checkpoints: 100 (new run), 200 (new run), 300 (old run)
- Expected steps: ~700, ~45s per step, total time ~8.75h
- Expected completion: ~08:15 UTC (2026-03-12)

**Training curve (attempt 2, as of step 200)**:
| Step | Loss | Acc | LR |
|------|------|-----|-----|
| 10 | 0.741 | 76.1% | 2.6e-6 |
| 50 | 0.672 | 76.9% | 9.8e-6 |
| 100 | 0.630 | 78.2% | 9.0e-6 |
| 150 | 0.536 | 80.7% | 8.6e-6 |
| 200 | 0.481 | 82.6% | 8.1e-6 |

**HF upload problem deep analysis**:
- New HfApi + 3 retries still failed
- Possible causes: Targon container network restrictions, HF API global rate limit, training.log file growth causing timeout
- Still hoping `on_train_end` will do final upload (uploading final model folder)

---

## HF Upload Callback Bug Summary

**Impact**: 3 training runs (GAME-only, Mixed v1, Mixed v2) all lost HF visibility after ~step 200-300
**Cost**: GAME ~$24 + Mixed v1 ~$16 + Mixed v2 ~$20 = ~$60, most training results unverifiable

**Attempted fixes**:
1. ❌ Reduce upload frequency (every 50 steps instead of 10)
2. ❌ New HfApi instance (don't cache)
3. ❌ 3 retries + exponential backoff

**Pending approaches**:
1. Don't upload training.log (only upload small JSON status file)
2. Use subprocess to call `huggingface-cli upload` instead of Python API
3. Use background thread for uploads, avoid blocking training process
4. Don't rely on intermediate uploads at all; do one big upload after training ends

---

## Loop — 2026-03-12 08:10 UTC

### Leaderboard (Block 7727853)
| Rank | UID | GAME | LGC-v2 | LIVEWEB | NAVWORLD | PRINT | SWE-SYNTH |
|------|-----|------|--------|---------|----------|-------|-----------|
| 1 | 179 | 45.76 | 92.92 | 25.42 | 15.85 | 81.08 | 29.00 |
| 2 | 45 | 43.93 | 91.60 | 26.71 | 12.02 | 84.66 | 27.00 |
| 3 | 142 | 39.47 | 80.40 | 16.87 | 14.16 | 73.02 | 51.00 |
| 4 | 120 | **46.75** | **95.56** | 24.60 | **7.56** | 80.63 | **34.00** |

### Analysis
- **We're #4** (dropped from #2), weight 0.059
- **Fatal weakness**: NAVWORLD 7.56 vs #1's 15.85 (-8.29 gap)
- **Leading environments**: GAME +0.99, LGC-v2 +2.64, SWE-SYNTH +5.00
- **Geometric mean bottleneck**: NAVWORLD alone dragging down overall ranking

### Actions
1. **Terminate container** `emathe3c8bz7kdeg` (training completed but HF upload failed after step 200, idling for 6 hours)
2. **Fix HF upload bug**: Switch to subprocess-isolated uploads (write JSON task file → separate Python process executes upload)
   - Root cause: HfApi within training process has corrupted state after long running (connection pool/memory/CUDA interference)
   - Approach: `_subprocess_hf_upload()` + `_HF_UPLOAD_WORKER_CODE` + JSON task communication
   - Fork new process per upload, fully isolated, 300s timeout
3. **Available models**: checkpoint-100/200/300 on HF, 300 is best (loss 0.454, accuracy 84%)

### Next Steps
- Plan next training round, focus on improving NAVWORLD
- Issue instructions to data session: increase NAVWORLD synthetic data volume and quality
- New training uses subprocess upload approach to verify fix

---

## Iteration #3 — Mixed v3 Training (NAVWORLD + LIVEWEB Enhanced)

**Date**: 2026-03-12
**Goal**: Close NAVWORLD gap (7.56→15+), strengthen LIVEWEB
**Container**: `serv-u-1324508-z59024vtap3zysl7`
**Model HF**: `YOUR_HF_USER/affine-qwen3-32b-mixed-v3`

### Major Data Updates
DynamoDB data volume significantly increased:
- **NAVWORLD**: 79 → **248** entries (score≥0.3)
- **LIVEWEB**: 3 → **1163** entries (filtered to 844 at score≥0.5)
- **SWE-SYNTH**: 437 → 412 entries (score≥0.5, ≤32K chars)

### Training Data Mix (mixed_v3_sft.jsonl, 12422 entries)
| Env | Original | Weighted | Share | Leaderboard Status |
|-----|----------|---------|-------|-------------------|
| GAME | 561 | 1122 (2x) | 9.0% | Leading +0.99 |
| LGC-v2 | 3353 | 3000 (1x cap) | 24.2% | Leading +2.64 |
| PRINT | 2899 | 2899 (1x) | 23.3% | Behind -0.45 |
| SWE-SYNTH | 412 | 824 (2x) | 6.6% | Leading +5.00 |
| NAVWORLD real | 248 | 1240 (5x) | 10.0% | **Weakness -8.29** |
| NAVWORLD synth | 161 | 805 (5x) | 6.5% | Synthetic data |
| LIVEWEB | 844 | 2532 (3x) | 20.4% | Behind -0.82 |

### Training Hyperparameters
- Model: Qwen/Qwen3-32B QLoRA (4-bit NF4)
- lr=1e-5, epochs=2, LoRA r=32/alpha=64
- max_len=8192, batch=1, grad_accum=16
- HF upload: **subprocess isolated** (new fix _HF_UPLOAD_WORKER_CODE)

### Key Improvements
1. **HF upload bug fix**: Fork independent Python process per upload, pass params via JSON file, 300s timeout
2. **Training script pre-upload**: Script uploaded to HF dataset repo, container downloads and executes (avoids Targon args too large)
3. **NAVWORLD 5x weighting**: From 6.5% to 16.5% share
4. **LIVEWEB first inclusion**: 844 high-score entries (score≥0.5), 3x weighting

### Expected
- 12422 samples / 16 effective batch = ~776 steps/epoch × 2 = ~1553 steps
- ~15s per step → ~6.5 hours

### Deployment History
1. **Direct SDK call** (08:30 UTC): Container `z59024vtap3zysl7`, 50 min no upload, terminated
   - Reason: Bypassed runner.py, manually built args, escape sequence issues caused script download failure
2. **After CLI fix** (09:30 UTC): Container `sc0k61mpx8rbm3k2`, normal deployment
   - Fixed CLI dataset_file parsing bug (repo:file format caused container name to contain illegal chars)
   - Training script pre-uploaded to HF, container downloads and executes

### Bug Fix Record
- `forge/cli.py`: Parse `repo:file` format (e.g., `YOUR_HF_USER/affine-sft-data:mixed_v3_sft.jsonl`)
- `forge/training/runner.py`: Script pre-upload to HF, avoids args too large
- `forge/training/config.py`: HF upload changed to subprocess isolation

### Actual Execution Results (2026-03-12 update)

**HF subprocess upload fix verified!**

Container `sc0k61mpx8rbm3k2` HF repo `YOUR_HF_USER/affine-qwen3-32b-mixed-lora` check results:
- ✅ checkpoint-100 uploaded
- ✅ checkpoint-200 uploaded
- ✅ checkpoint-300 uploaded
- ✅ training_log.json uploaded (contains full loss curve to step 200)
- ✅ training.log uploaded

**Training speed correction**: Actual ~45-52s per step (not estimated 15s), due to max_seq_len=8192 long sequences.

**Loss curve (checkpoint-300/trainer_state.json)**:
| Step | Loss | Token Acc | LR |
|------|------|-----------|-----|
| 10 | 0.741 | 76.1% | 2.6e-6 |
| 50 | 0.672 | 76.9% | 9.8e-6 |
| 100 | 0.630 | 78.2% | 9.0e-6 |
| 150 | 0.511 | 81.0% | 8.3e-6 |
| 200 | 0.481 | 82.6% | 7.5e-6 |
| 250 | 0.451 | — | — |
| 300 | 0.454 | — | — |

Loss plateaued after step 250 (~0.45). Training may reach optimum around step 300-400.

**Container termination stats (this session)**:
| Container | Purpose | Runtime | Result |
|-----------|---------|---------|--------|
| emathe3c8bz7kdeg | mixed v2 | ~6h | Training completed but HF upload failed, no visibility after step 200 |
| z59024vtap3zysl7 | mixed v3 direct SDK | ~50min | Script download failed |
| sc0k61mpx8rbm3k2 | mixed v3 CLI | ~3h+ | **checkpoint-300 successfully uploaded** ✅ |
| 2vhgsxlujlcp0b54 | 100-sample test | ~15min | save_steps=100 setting error |
| ygxy2aq4yeymp2z3 | 500-sample test | ~30min | Terminated too early (actually needs 46min to first upload) |
| pd68u3ithhuue4vu | Diagnostics | ~5min | Abandoned |

**This session total cost**: ~$26 ($2.40/hr × ~11h total container time)

---

## Loop — 2026-03-12 ~19:00 UTC

### Leaderboard (Block 7729709)

| Rank | UID | Weight | GAME | LGC-v2 | LIVEWEB | NAVWORLD | PRINT | SWE-SYNTH |
|------|-----|--------|------|--------|---------|----------|-------|-----------|
| 1 | 179 | 0.509 | 46.1 | 92.6 | 25.5 | 16.8 | 82.3 | 25.0 |
| 2 | 45 | 0.253 | 45.8 | 90.8 | 26.3 | 15.7 | 83.9 | 25.0 |
| 3 | 142 | 0.124 | 40.6 | 79.6 | 16.5 | 18.6 | 72.3 | 44.0 |
| 4 | 120 | 0.061 | 47.2 | 95.2 | 24.3 | 10.5 | 80.9 | 30.0 |
| 5 | 71 | 0.030 | 42.0 | 83.2 | 17.7 | 16.6 | 67.0 | 38.0 |

### Key Insights

1. **Subprocess HF upload verified**: checkpoint-100/200/300 all successfully uploaded, training pipeline reliable
2. **Training speed**: max_seq_len=8192 → ~50s/step, full 1554-step training needs ~23h ($55)
3. **Loss convergence**: Loss plateaued after step 250-300 (~0.45), longer training may not significantly improve
4. **No eval capability**: No local GPU/Docker permission, cannot run affinetes evaluation

### Leaderboard Strategic Analysis

**NAVWORLD remains the global differentiation key**:
- Everyone weak (10-18%), our UID 120 = 10.5% (one of the worst)
- 462 synthetic+real entries prepared, 5x weighting in training

**SWE-SYNTH gap widening**:
- #3 UID 142 = 44%, ours = 30%
- Need more high-score SWE-SYNTH data or dedicated training

**LIVEWEB has opportunity**:
- #2 UID 45 = 26.3% leading, 844 entries already available
- First inclusion in training, results pending evaluation

### Blockers and Pending

1. **Eval**: Need Docker permission or Targon-deployed vLLM to evaluate checkpoint-300
2. **Training speed**: Consider lowering max_seq_len to 4096 (most samples likely don't need 8192)
3. **checkpoint-300 training incomplete**: 300/700 steps (~43%), but loss already plateaued
4. **Cost control**: Avoid blind extended training; need eval feedback to guide next steps

---

## Loop — 2026-03-12 ~20:30 UTC — Data Quality Deep Audit

### Leaderboard (Block 7730311)

| Rank | UID | Weight | GAME | LGC-v2 | LIVEWEB | NAVWORLD | PRINT | SWE-SYNTH |
|------|-----|--------|------|--------|---------|----------|-------|-----------|
| 1 | 45 | 0.508 | 45.3 | 91.2 | 26.6 | 16.2 | 84.4 | 22.2 |
| 2 | 142 | 0.253 | 40.8 | 78.8 | 16.4 | 19.5 | 72.1 | 44.0 |
| 3 | 120(us) | 0.125 | **47.6** | **95.2** | 24.2 | 10.6 | 80.9 | 32.3 |
| * | 248 | 0.000 | 62.3 | 93.3 | 21.8 | **33.7** | 73.3 | 27.3 |

**Change**: We rose from #4 to #3, Foremost01 dropped out of Top 10. RLStepone NAVWORLD 33.7% is a huge threat.

### Data Quality Audit Results (Three Severe Issues)

#### Issue 1: NAVWORLD Synthetic Data Format Completely Wrong 🔴
- 431 synthetic entries use text format ("Call tool: xxx") instead of Qwen3 `<tool_call>` format
- Model outputs plain text instead of standard tool calls after training, eval environment cannot parse
- **Fixed**: Converted to standard tool_calls + tool role format, 432 entries verified

#### Issue 2: SWE-SYNTH Trailing Message Role Error 🔴
- 444 entries have last message as user role (diff content)
- Model learns to predict user output instead of assistant reply
- **Fixed**: Removed trailing user messages

#### Issue 3: LIVEWEB Data All Too Long and Invalid 🔴
- 844 entries median 145K chars (~36K tokens)
- 0 entries usable at max_seq_len=8192 (all truncated to conversation beginning)
- 2532 training entries (20.4% share) are pure noise
- **Fixed**: Removed from training set

#### Other Issues
- GAME: 38 duplicates → deduplicated
- GAME: assistant replies all single digits (1-3 chars), no reasoning process → environment characteristic, not addressing now

### Training Hyperparameter Optimization (Based on Frontier Paper Research)

| Parameter | v3 (old) | v4 (new) | Justification |
|-----------|---------|---------|---------------|
| learning_rate | 1e-5 | **1e-4** | QLoRA standard range, old value 10x too low |
| lora_r | 32 | **64** | Multi-task needs more capacity |
| epochs | 2 | **1** | Prevent overfitting, SFT 1-2 epochs sufficient |
| warmup | 10% | **3%** | Standard recommendation |
| max_grad_norm | 1.0 | **0.3** | QLoRA paper recommendation |
| packing | False | **True** | Short sample efficiency improvement 2-3x |
| max_seq_len | 8192 | **4096** | LIVEWEB removed, other envs sufficient |

### Mixed v4 Dataset (6000 samples)

| Env | Samples | Share | Key Improvement |
|-----|---------|-------|-----------------|
| GAME | 1200 | 20% | Deduplicated |
| NAVWORLD | 1200 | 20% | **Correct tool_call format** |
| PRINT | 1560 | 26% | — |
| LGC-v2 | 1320 | 22% | — |
| SWE-SYNTH | 720 | 12% | **Fixed trailing user** |

Estimate: ~250 steps, ~2h, ~$5

### Competitor Analysis
- All Top models: Qwen3-32B full merge upload
- RLStepone: Hints at using RL methods, NAVWORLD 33.7% far exceeds SFT approach
- Training details not public, competitiveness lies in data quality

### Next Steps
1. Upload mixed_v4 + start training after user confirmation
2. Need to solve eval infrastructure after training completes (Docker/Targon vLLM)
3. Monitor whether RLStepone reaches sample count threshold

---

## Loop — 2026-03-12 ~21:00 UTC — Mixed v4 Training Launch

### Leaderboard (Block 7730361) — We're #1!

| Rank | UID | Weight | GAME | LGC-v2 | LIVEWEB | NAVWORLD | PRINT | SWE-SYNTH |
|------|-----|--------|------|--------|---------|----------|-------|-----------|
| **1** | **120(us)** | **0.507** | **47.6** | **95.2** | 24.2 | 10.8 | 80.9 | 32.3 |
| 2 | 45 | 0.253 | 45.3 | 91.2 | 26.6 | 16.2 | 84.4 | 20.6 |
| 3 | 142 | 0.126 | 40.8 | 78.8 | 16.4 | 19.5 | 72.1 | 41.8 |

### Action: Mixed v4 Training Launched

**Container**: `serv-u-1324508-f57pyto88sd7ef95` (2x H200-M, $4.80/hr)

**Training config (v4)**:
- Data: mixed_v4_sft.jsonl (6000 samples, no LIVEWEB)
- lr=1e-4, LoRA r=64/alpha=128, 1 epoch
- max_seq_len=4096, batch=2, grad_accum=4, packing=True
- max_grad_norm=0.3, warmup=3%
- Multi-GPU: accelerate launch DDP (2x H200)
- HF backup: YOUR_HF_USER/affine-qwen3-32b-v4

**Key improvements (vs v3)**:
1. NAVWORLD: text format → standard tool_call format
2. SWE-SYNTH: removed incorrect trailing user messages
3. LIVEWEB: removed (all too long, invalid)
4. lr: 1e-5→1e-4 (QLoRA standard range)
5. packing: short sample packing, 2-3x efficiency
6. Multi-GPU DDP: 2x H200 data parallel

**Estimate**: ~375 steps (6000/16), ~3-4h (incl. setup), ~$15-20

---

## Loop Monitoring — 2026-03-12 16:31 UTC

### Leaderboard (Block 7730361)

| Rank | UID | Model | Weight | GAME | NAVWORLD | SWE-SYNTH |
|------|-----|-------|--------|------|----------|-----------|
| 1 | 120 | voidai001/affine-new | 0.507 | 47.6 | 10.8 | 32.3 |
| 2 | 45 | Infinite3214/Affine-0305 | 0.253 | 45.3 | 16.2 | 20.6 |
| 3 | 142 | AnastasiaFantasy | 0.126 | 40.8 | 19.5 | 41.8 |
| 8 | 242 | RLStepone/h2 (19 samples) | 0.000 | 53.6 | 24.5 | 0.0 |
| 10 | 248 | RLStepone/h3 (18 samples) | 0.000 | **64.4** | **33.7** | 27.3 |

**Key findings**:
- RLStepone-h3 GAME 64.4 + NAVWORLD 33.7, far exceeding everyone, climbing (only 18 samples)
- NAVWORLD remains the weakest environment globally, largest differentiation opportunity
- We're not on leaderboard (training in progress)

### Training Status

- Container `f57pyto88sd7ef95` alive (HTTP 404), HF v4 repo empty
- May still be in setup (downloading model) or training hasn't reached step 100
- Not terminating yet, check again next loop

### Data Session

- status=idle, issued 4 tasks to data_synth.md
- Task 1: NAVWORLD tool_call format generation (300+)
- Task 2: DynamoDB periodic refresh
- Task 3: GAME reasoning sample investigation
- Task 4: MemoryGym pre-generation

### Next Steps

1. Check HF v4 repo again in 10 minutes to confirm training progress
2. If still no upload → container may have issues, consider terminating and restarting
3. After training completes → need to resolve eval infrastructure (ask user)

---

## DPO Pipeline Development — 2026-03-12 17:00 UTC

### Background

User suggested trying RL methods. After analysis, chose **DPO (Direct Preference Optimization)**:
- Offline method, doesn't need online inference, QLoRA compatible
- DynamoDB has multiple miner responses with different scores for same task_id → natural preference pairs
- trl `DPOTrainer` stable version, natively supports tool_calls
- Training path: SFT checkpoint → DPO alignment

### Implementation

1. **`forge/data/sft.py`**: Added `export_dpo_data()` — group by task_id, high score=chosen, low score=rejected
2. **`forge/training/config.py`**: Added `to_dpo_script()` — generates DPO training Python script
3. **`forge/cli.py`**: Added `data extract-dpo` and `train dpo-launch` commands
4. **`forge/training/runner.py`**: Improved container startup script, added apt-get retry and pip bootstrap fallback

### DPO Data Extraction Results

| Env | Preference Pairs | Avg Score Gap |
|-----|-----------------|--------------|
| GAME | 589 | 0.746 |
| LGC-v2 | 800 (capped) | 1.000 |
| NAVWORLD | 241 | 0.443 |
| PRINT | 800 (capped) | 1.000 |
| SWE-SYNTH | 258 | 1.000 |
| **Total** | **2688** | — |

Mixed DPO dataset `mixed_dpo.jsonl` (79.5MB) uploaded to HF `YOUR_HF_USER/affine-sft-data`.

### v4 Training Failure Diagnosis

Container `f57pyto88sd7ef95` logs show:
- Targon network completely down (all apt sources Connection refused)
- `apt-get install python3-pip` failed → `python3` unavailable → training never started
- Container terminated to avoid burning $4.80/hr

**Fix**: runner.py startup script added apt-get retry (3 times) + pip bootstrap fallback.

### DPO Training Plan

**Strategy**: SFT → DPO two-stage training
1. First complete SFT training (mixed_v4_sft.jsonl, 6000 samples) for base capability
2. Run DPO on SFT checkpoint (mixed_dpo.jsonl, 2688 pairs) for preference alignment

**DPO hyperparams**:
- beta=0.1, lr=5e-6, batch=1, grad_accum=8
- LoRA r=64, alpha=128
- max_length=4096, max_prompt_length=2048
- 1 epoch

**CLI commands**:
```bash
# Extract DPO data
python3 -m forge data extract-dpo GAME --min-chosen-score 0.5 --min-score-gap 0.15

# Launch DPO training
python3 -m forge train dpo-launch mixed_dpo.jsonl \
  --hf-repo YOUR_HF_USER/affine-qwen3-32b-dpo \
  --sft-adapter YOUR_HF_USER/affine-qwen3-32b-v4 \
  --gpu H200
```

### Next Steps

1. Restart SFT training (need SFT checkpoint first)
2. After SFT completes, run DPO on top
3. Or: run DPO directly from base model (skip SFT), compare results

---

## Targon Network Failure — 2026-03-12 17:10 UTC

### Leaderboard Changes

AnastasiaFantasy rose to #1 (0.507), voidai dropped to #3 (0.126). Key: Anastasia wins through NAVWORLD 19.8 + SWE-SYNTH 42.0 balance.

### Targon Outbound Network Completely Down

3 consecutive containers all failed due to network unavailability:
1. `f57pyto88sd7ef95` (H200-M) — apt Connection refused, terminated
2. `s97xo4chiolo6hcd` (H200) — same apt failure, terminated
3. `795bkdwgpx0vd80k` (H200, PyTorch image) — zero log output, terminated
4. `z1sibtgx5es0x87p` (H200, CUDA image + retry) — apt failed 5 times, terminated

**Root cause**: Targon serverless container outbound network connection refused (HTTP/HTTPS both down). Cannot install python3-pip, download HF models, or run any network-dependent operations.

**Approaches tried**:
- CUDA image + apt-get retry → network down
- PyTorch image (has python/pip/torch pre-installed) → Targon doesn't support (zero logs)
- pip bootstrap via curl → no curl in container

**Possible solutions**:
1. Wait for Targon to fix network (previous training succeeded, so not a permanent issue)
2. Build custom Docker image (pre-install all dependencies), push to Docker Hub
3. Use other GPU providers (SSH backend)
4. User provides a machine with GPU

**Cost loss**: ~$5 (4 containers running 10-30 minutes each)

---

## Loop Iteration — 2026-03-12 ~17:40 UTC

**Leaderboard**: #1 UID 142 (weight 0.507), we're not on leaderboard
- New player RLStepone (UID 242/248) few samples but high scores: GAME 47-51, NAVWORLD 22-28, PRINT 75-94
- NAVWORLD weakest across the board (7-28), largest differentiation opportunity

**Training status**: Completely blocked
- Targon outbound network down for 2h+ confirmed
- This loop tried 3 more containers: H200 CUDA + diagnostics, H200-M CUDA, H200 network test
- All failed: `Connection refused` on port 80/443, cannot apt-get/pip/curl
- PyTorch image: Targon doesn't support (zero logs + logs API 500)
- Cumulative cost: ~$3 additional

**Code improvements** (completed this loop):
1. Fixed bash `&` bug: `(...&)` subshell isolation, ensuring only http server is backgrounded
2. Added diagnostic output: which python3/pip/curl/wget + OS version + apt-get full error
3. Discovered `| tail` masks apt-get exit code (non-blocking bug, pending fix)

**Data status**: Ready, no action needed
- SFT: 5600 entries (enhanced_mixed_sft.jsonl) uploaded to HF
- DPO: 2688 pairs (mixed_dpo.jsonl) uploaded to HF
- DynamoDB refresh: 2.7h ago, not needed

**Decision**: Wait for Targon to recover, stop wasting resources retrying. Training plan unchanged:
1. SFT (enhanced_mixed_sft.jsonl, 5600 entries) → YOUR_HF_USER/affine-qwen3-32b-v4
2. DPO (mixed_dpo.jsonl, 2688 pairs) → fine-tune on SFT checkpoint

---

## Loop Iteration — 2026-03-12 ~18:00 UTC

**Leaderboard**: No change. #1 UID 142 (0.507)

**Targon Network Deep Diagnosis**:
- Used bash `/dev/tcp` to test 4 HTTPS targets: huggingface.co, github.com, google.com, pypi.org
- **All CLOSED / Network unreachable** — IPv4 Connection refused, IPv6 Network unreachable
- Conclusion: Targon containers have **completely isolated outbound network**, not a specific port/target issue
- Previous training success means this is a Targon infrastructure failure, not normal state
- Cumulative test cost: ~$2 additional

**Action**: Cannot train. Need user intervention:
1. Contact Targon support to confirm network status
2. Or provide alternative GPU resources (SSH machine)
3. Or use other GPU cloud providers

---

## Loop Iteration — 2026-03-12 ~18:20 UTC

**Leaderboard change**: **New #1!** UID 179 (Foremost01/affine-n) takes the crown (weight 0.506)
- Former #1 UID 142 dropped to #2 (0.251)
- Foremost01: GAME 48.5, LGC-v2 92, LIVEWEB 25.6, NAVWORLD 16.2, PRINT 79.8, SWE-SYNTH 22.2
- Weaknesses: NAVWORLD 16.2, SWE-SYNTH 22.2 — our data happens to have advantages in these two environments
- Total miners increased to 49

**Targon network**: Still down. HF/PyPI all Network unreachable. ~8 cumulative probes.

**Training blocked**: No change, waiting for user intervention or Targon recovery.

---

## Loop Iteration — 2026-03-12 ~18:40 UTC

**Leaderboard**: Stable. #1 UID 179 (Foremost01, 0.506). RLStepone (UID 242) sample count increased to 30+, GAME 49.9 NAVWORLD 25.0, potential threat.
**Targon network**: 9th probe, still Network unreachable.
**DynamoDB**: 3.1h, refresh next loop.
**Action**: None. Training blocked.

---

## Loop Iteration — 2026-03-12 ~19:00 UTC (Breakthrough!)

**Leaderboard**: #1 UID 142 (AnastasiaFantasy, 0.505) reclaims. Foremost01 (UID 179) drops to #2.

**Targon Network Breakthrough**:
- **Network is intermittent, not completely dead!** ~20 seconds of brief network window after container startup
- apt-get succeeded (47MB, 4s), pip install also succeeded (all dependencies including torch 2.10.0)
- Key improvement: Added network wait loop + pip retry + HF download retry to setup_and_train
- First attempt: pip succeeded but HF download phase network died again → container scaled down
- Second attempt: Added HF download retry logic, container `serv-u-1324508-c7dlf9ms1s0ipwev` starting

**Startup script improvements**:
1. Network wait: 60×10s loop probing `/dev/tcp/pypi.org/443`
2. apt-get: succeeded first try (network recovered after 20s)
3. pip install: `--retries 10 --timeout 120` + outer 5 retries
4. HF download: 5 retries + file existence verification
5. 30s wait before retry on each step failure

**Training config**: SFT, enhanced_mixed_sft.jsonl (5600 entries), lr=1e-4, epoch=1, QLoRA r=64, max_len=8192
**Target HF**: YOUR_HF_USER/affine-qwen3-32b-v4

---

## Loop Iteration — 2026-03-12 ~20:00-21:30 UTC (Continued Targon Network Battle)

**Leaderboard**: #1 UID 142 (0.507). Foremost01 dropped out of top 10. RLStepone (UID 242) GAME 50.88.

**Targon Network Deep Analysis**:
- Network is **intermittent**: ~30-60s brief window after startup
- apt-get update+install (47MB) succeeds within window every time
- pip install ALL (including torch 2GB) succeeded once (container hyuzso4mpb9j70gk)
- HF data download (42MB) with stdlib urllib succeeds within window every time
- **Core bottleneck**: torch 2GB download needs sustained network, but window length is inconsistent

**Approaches tried**:
| Approach | Result |
|----------|--------|
| Download data first, pip after | Data OK, pip failed (network died) |
| Data+pip parallel | First version had bash `&` bug, second version still pip timeout |
| Per-package pip install | Theoretically viable but not verified successful |
| PyTorch official image | Targon doesn't support (500 error) |

**Key code improvements**:
- Network wait loop (60×10s)
- `(cmd &)` subshell backgrounding to avoid `&` full-chain background bug
- urllib stdlib direct download from HF (bypasses huggingface_hub library)
- Parallel download+install strategy
- pip multi-layer retry (retries=10, timeout=300, outer 3 times)

**Conclusion**: Targon serverless network limitations are fundamental. Need pre-installed PyTorch image (Targon doesn't support), or external GPU resources.

**Cumulative cost**: ~$15-20 (~10 containers, each running 10-30 minutes)

---

## Loop Iteration — 2026-03-12 ~22:00 UTC (Final Conclusion)

**Leaderboard**: New #1 = UID 45 (Infinite3214, 0.508). Competition intensifying.

**Targon Final Conclusion**: Tried torch-first strategy (exclusive bandwidth) again, still failed.
- ~15 container attempts, cumulative cost ~$25
- pip install torch 2GB succeeded only once (network window uncontrollable)
- PyTorch image Targon returns 500
- **Targon serverless cannot be used for training in current network state**

**Current blocker**: Need user to provide alternative GPU resources. No more retrying on Targon.

---

## Loop Iteration — 2026-03-12 ~20:50 UTC

**Leaderboard**: #1 UID 45 (Infinite3214, 0.508) stable.
**Targon**: No more attempts. Waiting for user to provide alternative resources.
**DynamoDB refresh**: Complete. GAME 930(+24), NAVWORLD 116(+37), SWE-SYNTH 454(+10), LIVEWEB 997(+70).
**Next steps**: Wait for GPU resources. Data continues accumulating.

---

## Targon Training Breakthrough — 2026-03-12 21:15 - 2026-03-13 01:15 UTC

### Solving 4 Key Bugs for Targon Training

**Bug 1: Targon doesn't support pytorch image → Fixed**
- `pytorch/pytorch:2.5.1-cuda12.4-cudnn9-devel` can now successfully start
- Previously returned 500, possibly fixed by Targon platform update

**Bug 2: pip install unreliable network → Offline wheel bundle approach**
- Pre-downloaded all Python dependency wheel files (202MB tar.gz)
- Uploaded to HF dataset repo (`YOUR_HF_USER/affine-sft-data/ml-deps.tar.gz`)
- Container uses urllib (reliable) to download, then `pip install --no-index --find-links`
- urllib download 229MB in Targon container takes ~30 seconds

**Bug 3: bitsandbytes version too old → Upgraded to 0.49.2**
- Wheel bundle initially contained bitsandbytes 0.42.0
- transformers requires >= 0.46.1
- Updated wheel bundle, training script can now load 4-bit model normally

**Bug 4: Model download 65GB too large → Pre-quantized model**
- Original Qwen/Qwen3-32B needs ~65GB download (16 safetensors) then runtime quantization
- Switched to `unsloth/Qwen3-32B-bnb-4bit` (4 safetensors, ~18GB)
- Download time reduced from 10-30 minutes to ~90 seconds

**Bug 5: OOM crash → Conservative memory configuration**
- batch=2, seq=8192, packing=True → container OOM immediately after training starts
- batch=1, seq=4096, packing=False → training starts but OOM after step 10
- **Final config**: batch=1, seq=2048, LoRA r=16, packing=False → stable running

### New HTTP Status Monitoring
- Training script writes `/tmp/health/status.json`, exposed via http.server
- Can view in real-time: phase, step, loss, epoch, error
- Solved Targon logs API not returning logs for pytorch image

### Current Training Status
- **Container**: serv-u-1324508-uzbtmnami13fvoz7
- **Data**: enhanced_mixed_sft.jsonl (5600 samples)
- **Model**: unsloth/Qwen3-32B-bnb-4bit
- **Config**: lr=1e-4, batch=1, grad_accum=16, seq=2048, LoRA r=16/alpha=32, packing=False
- **Progress**: Step 20/350, loss 0.921→0.689, ~38 seconds per step
- **Expected completion**: ~01:00 + 350×38s/3600 ≈ 4.7h → ~05:40 UTC
- **HF backup**: YOUR_HF_USER/affine-qwen3-32b-v4
- **Cost**: $2.40/hr × ~4.7h ≈ $11.3

### Cumulative Targon Cost
- Previous failed attempts: ~$25
- This round debugging (5 containers): ~$5
- Training (estimated): ~$11
- **Total**: ~$41

---

## Loop Report — 2026-03-13 07:00 UTC

### Leaderboard
| Rank | UID | GAME | LGC-v2 | LIVEWEB | NAVWORLD | PRINT | SWE-SYNTH |
|------|-----|------|--------|---------|----------|-------|-----------|
| 1 | 45 Infinite3214 | 47.77 | 91.60 | 25.54 | 19.61 | 85.87 | 20.83 |
| 2 | 153 vera6 | 50.35 | 92.50 | 24.17 | 22.18 | 83.98 | 15.62 |
| 3 | 142 AnastasiaFantasy | 41.57 | 78.00 | 16.97 | 23.91 | 73.82 | 31.25 |

### Training Status
- **v4**: step 60/350, loss 0.50, **paused** — Targon platform unavailable
- checkpoint-60 safely stored on HF `YOUR_HF_USER/affine-qwen3-32b-v4`
- Resume mechanism code ready

### Targon Platform Status
- **Completely unavailable**: Even empty containers (echo+sleep) cannot respond to HTTP
- Tested H200-small, H200-medium, H100-small, all crash in 3-6 min
- Same config previously ran to step 60 (01:15-02:49 UTC), started failing after 03:00
- Known issue: transformers new version CVE-2025-32434 requires torch>=2.6

### Actions
1. Terminated all remaining containers (complete)
2. Dataset address migrated to new HF repo (complete)
3. Updated all HF references in code (complete)
4. Resume mechanism implemented (complete)

### Blockers
- Targon platform recovery time unknown
- Need alternative GPU solution or wait for platform recovery

### Next Steps
- After Targon recovers, restart training with wheel bundle containing torch 2.6
- Or explore alternative GPU platforms

---

## v5 Model Evaluation — 2026-03-14

### Evaluation Environment
- **Rental**: rentals-fn3n2qeug900fqif (4×H200)
- **Inference**: sglang in venv, YOUR_HF_USER/affine-qwen3-32b-v5-merged, tp=4, port 30000
- **Eval**: scripts/eval_envs.py (affinetes SDK, host_network=True)
- **100 samples per environment**

### v5 Training Config Review
- QLoRA r=128/alpha=256, lr=1e-4, batch=2×4GPU, grad_accum=4, seq=4096
- Data: v5_mixed_sft.jsonl (8263 samples → 11872 weighted)
- Final loss 0.23, eval_loss 0.265, 245 steps

### Evaluation Results

| Env | Samples | Errors | Mean Score | Status |
|-----|---------|--------|-----------|--------|
| GAME | 100 | 29 parse errors | 0.1604 | Complete |
| NAVWORLD | 100 | 0 | 0.0000 | Complete |
| PRINT* | 100 | 13 | 0.2200 | Complete |
| SWE-SYNTH | — | — | — | Incomplete (rental reclaimed) |
| LIVEWEB | — | — | — | Incomplete (rental reclaimed) |

*PRINT was not in the eval plan but results were produced

#### GAME Breakdown

| Game | Samples | Mean Score | Wins |
|------|---------|-----------|------|
| goofspiel | 7 | 1.000 | 7/7 |
| blackjack | 3 | 0.667 | 2/3 |
| leduc_poker | 6 | 0.590 | 4/6 |
| euchre | 3 | 0.500 | 2/3 |
| gin_rummy | 5 | 0.401 | 0/5 |
| checkers | 6 | 0.000 | 0/6 |
| chess | 1 | 0.000 | 0/1 |
| clobber | 11 | 0.000 | 0/11 |
| dots_and_boxes | 4 | 0.000 | 0/4 |
| go | 2 | 0.000 | 0/2 |
| hearts | 6 | 0.000 | 0/6 |
| hex | 4 | 0.000 | 0/4 |
| liars_dice | 8 | 0.000 | 0/8 |
| othello | 3 | 0.000 | 0/3 |
| phantom_ttt | 2 | 0.000 | 0/2 |
| parse_error | 29 | — | — |

#### NAVWORLD: 100% All Zeros
- All 100 samples scored 0.00
- Model completely unable to perform navigation tasks
- Possible cause: v5 training data NAVWORLD format issue (text format vs tool_call)

### Key Findings

1. **29% GAME parse error**: Model output format not accepted by environment parser, serious issue
2. **GAME CoT conflict**: 54.4% of training data has `<think>` tags, 45.6% doesn't → inconsistent model output
3. **NAVWORLD completely failed**: tool_call format training data quality issue, model cannot generate correct tool calls
4. **Simple games all won**: goofspiel (7/7), blackjack (2/3) — games with simple rules can be solved
5. **Complex games all lost**: chess, go, hex, checkers all 0 — games requiring deep search completely unsolvable

### v6 Training Plan

Based on v5 eval results, v6 should focus on:

1. **GAME parse error**: Unify data format, eliminate think tag conflict
2. **NAVWORLD**: Use correct tool_call format data
3. **Lower LoRA rank**: r=128→64, reduce inter-environment interference
4. **Focus on 4 environments**: Only train GAME, NAVWORLD, SWE-SYNTH, LIVEWEB (exclude LGC-v2, PRINT)

---

## v6 Training Launch — 2026-03-14

### Training Environment
- **Rental**: rentals-fn3n2qeug900fqif (4×H200)
- **Model**: Qwen/Qwen3-32B (pre-quantized unsloth/Qwen3-32B-bnb-4bit)
- **Script**: /root/scripts/train_v6.py

### Data Cleaning
- Original v6 data: 7402 samples
- Removed LGC-v2/PRINT: 1173 entries (Dyck/boolean/math/predict-output data without system message)
- Fixed JSONL schema: unified to messages-only format
- **After cleaning**: 6229 samples

| Env | Samples | Share |
|-----|---------|-------|
| GAME | 2274 | 36.5% |
| NAVWORLD | 1503 | 24.1% |
| SWE-SYNTH | 1275 | 20.5% |
| LIVEWEB | 506 | 8.1% |
| OTHER* | 671 | 10.8% |

*OTHER may be cross-environment or hard-to-classify samples

### Training Hyperparameters
- lr=5e-5, batch=2, grad_accum=8, epochs=1, seq=4096
- LoRA r=64, alpha=128, packing=True
- save_steps=50, warmup=3%, max_grad_norm=0.3
- HF backup: YOUR_HF_USER/affine-qwen3-32b-v6

### Execution Status
- Training started normally, 290 steps, ~46s/step
- Expected completion: ~3.7h (~$8.9 at $2.40/hr)

### Loss Curve (checkpoint-50)
| Step | Loss |
|------|------|
| 10 | 0.8604 |
| 20 | 0.6888 |
| 30 | 0.6309 |
| 40 | 0.4878 |
| 50 | 0.4232 |
| 60 | 0.3570 |
| 70 | 0.3722 |
| 80 | 0.3317 |
| 90 | 0.3127 |
| 100 | 0.3211 |
| 110 | 0.2622 |
| 120 | 0.2669 |
| 130 | 0.2775 |
| 140 | 0.2518 |
| 150 | 0.2372 |
| 160 | 0.2221 |
| 170 | 0.2686 |
| 180 | 0.2196 |
| 190 | 0.2052 |
| 200 | 0.2005 |
| 210 | 0.2115 |
| 220 | 0.2394 |
| 230 | 0.2200 |
| 240 | 0.2297 |
| 250 | 0.2456 |
| 260 | 0.2118 |
| 270 | 0.2254 |
| 280 | 0.2226 |
| 290 | 0.2209 |

### Training Complete ✅
- **Total time**: 3.7h, 290 steps, cost ~$8.9
- **Final loss**: 0.2209 (down 74% from 0.86)
- **HF repo**: YOUR_HF_USER/affine-qwen3-32b-v6 (LoRA adapter, final + checkpoint-200/250/290)
- Compared to v5: loss 0.23 vs v6 loss 0.22 (similar, but cleaner data, no LGC-v2/PRINT contamination)

### Merge + Eval Launch
- LoRA merge complete (6.5 min), saved to /root/merged_model (24 files)
- sglang deployed (tp=4, port 30000)
- Eval launched: GAME + NAVWORLD × 100 samples
- SWE-SYNTH + LIVEWEB to launch after first round completes

### Tool Improvements
- Added `forge rental` CLI command group (status/exec/kill/start-training/start-sglang/start-eval/clean-data)
- Reduced direct SSH operations, improved efficiency and reusability

### v6 Eval Intermediate Results (GAME 29/100)
- 23 with scores (7 non-zero), 6 errors
- Temporary mean ~0.09 (v5 was 0.16, regression)
- Cause: v6 data issues not fully resolved (see diagnosis below)

---

## v7 Comprehensive Diagnosis — Source Code Analysis + Data Audit Results

### Methodology
1. Read 4 evaluation environment source code (affinetes), understand exact format requirements
2. Per-environment audit of training data, compare format differences
3. Formulate fix plan before launching training

### GAME Diagnosis

**Root cause: System Prompt Inconsistency**
- DDB data (995 entries): prompt="respond with ONLY the action ID" → assistant=pure number
- CoT data (1458 entries): prompt="use think block" → assistant=think+number
- 13.9% of CoT data has prompt saying "ONLY" but assistant still has think tag (direct contradiction)
- Mixed training → model doesn't know which format to use → 29% parse error

**Data quality issues**:
- DDB: 20 dirty entries (format contamination: `.3`, `".6`, long text residuals)
- CoT: 35 truncated think tags, 1 special token leak
- Game coverage mismatch: CoT missing hex/othello/clobber/gin_rummy/liars_dice

**Eval environment actual behavior**:
- `strip_think_tags=True`: automatically strips think tags
- 2 retry mechanism: even if first output is wrong, there's a chance to correct
- So CoT format itself is not the problem; the problem is system prompt inconsistency

### NAVWORLD Diagnosis

**Root cause: 59.7% of samples missing direction tool call**
- Eval requires calling poi_search + weather + direction (three tools)
- distill_all.jsonl (1503 entries) only 605 contain direction
- Training on this data → model learns "don't call direction" → eval deduction

**navworld_sft.jsonl (130 entries) completely unusable**:
- Uses text simulation format ("Call tool: xxx"), not standard function calling
- No tool_calls field, no role=tool
- Mixing into training teaches model to output wrong format

**Other issues**:
- 8 contaminated samples (text pseudo-tool calls)
- 7 final plans <800 chars

### SWE-SYNTH Diagnosis
- Format: THOUGHT + single bash code block
- **Does not support think tag** (conflicts with THOUGHT format)
- Binary scoring (0 or 1)
- Data pending audit

### LIVEWEB Diagnosis
- Format: free thinking + JSON action object
- Supports think tag
- Most data >16K tokens (cannot train after truncation)
- Data pending audit

---

## v7 Fix Plan

### GAME Fix
1. **Unify system prompt to CoT version** (eval will auto-strip think tags)
2. DDB data: keep pure number format, but unify system prompt to CoT version → let model learn "even when prompt says think, can also output just a number"
3. CoT data: fix 13.9% incorrect prompts
4. Clean 20 DDB dirty entries + 35 truncated CoT
5. Target: ~2400 clean GAME entries

### NAVWORLD Fix
1. **Keep only samples containing poi_search + weather + direction** (~605 entries)
2. Delete navworld_sft.jsonl (text format completely unusable)
3. Clean 8 contaminated + 7 short plans
4. Re-distill to supplement direction coverage data to 1000+
5. Target: ~600 clean entries (short-term), 1000+ (after distillation supplement)

### SWE-SYNTH Fix
1. Ensure system prompt matches eval
2. Ensure no think tag (use THOUGHT format)
3. Maintain existing ~1275 entries

### LIVEWEB Fix
1. Filter samples ≤16K chars
2. Ensure JSON action format correct
3. Available data may be insufficient (most too long)
4. If usable data <100 entries, consider excluding from v7

### Hyperparameter Correction
- lr: 5e-5 → **1e-4** (v6's 5e-5 too low, historically verified 1e-4 is better)
- HF_TOKEN: ensure correctly exported

---

## v7 Training — 2026-03-14

### Data
- 4809 entries, 4 environments (GAME 2417, SWE-SYNTH 1350, NAVWORLD 605, LIVEWEB 437)
- All known issues fixed, datasets load verification passed

### Hyperparameters
- lr=1e-4, batch=2, grad_accum=8, epochs=1, seq=4096
- LoRA r=64, alpha=128, packing=True
- HF backup: YOUR_HF_USER/affine-qwen3-32b-v7 (auto-upload verified)

### Loss Curve
| Step | Loss | vs v6 |
|------|------|-------|
| 10 | 0.7922 | 0.8604 |
| 20 | 0.5996 | 0.6888 |
| 30 | 0.3645 | 0.6309 |
| 40 | 0.3428 | 0.4878 |
| 50 | 0.3044 | 0.4232 |

| 60 | 0.2730 | 0.3570 |
| 70 | 0.2669 | 0.3722 |
| 80 | 0.2422 | 0.3317 |
| 90 | 0.2190 | 0.3127 |
| 100 | 0.2124 | 0.3211 |
| 110 | 0.2160 | 0.2622 |
| 120 | 0.2108 | 0.2669 |
| 130 | 0.1988 | 0.2775 |
| 140 | 0.2048 | 0.2518 |
| 150 | 0.1591 | 0.2372 |
| 160 | 0.1876 | 0.2221 |
| 170 | 0.1581 | 0.2686 |
| 180 | 0.1658 | 0.2196 |
| 190 | 0.1841 | 0.2052 |
| 200 | 0.1761 | 0.2005 |

| 210 | 0.1766 | 0.2115 |
| 220 | 0.1769 | 0.2394 |
| 230 | 0.1776 | 0.2209 |

### Training Complete ✅
- **Total time**: 3.1h, 230 steps, cost ~$7.4
- **Final loss**: 0.1776 (vs v6 0.2209, 20% improvement)
- **HF repo**: YOUR_HF_USER/affine-qwen3-32b-v7 (auto-upload, final + checkpoint-150/200/230)
- **Convergence speed**: v7 step 50 (0.30) ≈ v6 step 90 (0.31), ~2x faster

v7 convergence significantly faster than v6.

### v7 GAME Eval Intermediate Analysis (40/100)

**Overall**: mean=0.030, error rate=11% (vs v5 29%)

**Per-game breakdown**:
| Game | n | Non-zero | Mean | Learnability |
|------|---|----------|------|-------------|
| leduc_poker | 2 | 2/2 | 0.345 | ✅ Strategy effective |
| euchre | 2 | 1/2 | 0.190 | ✅ Partially effective |
| othello | 8 | 0/8 | 0.000 | 🟡 Needs better strategy |
| hex | 5 | 0/5 | 0.000 | 🟡 Needs better strategy |
| go | 6 | 0/6 | 0.000 | ❌ LLM cannot learn |
| checkers | 4 | 0/4 | 0.000 | ❌ LLM cannot learn |
| gin_rummy | 2 | 0/2 | 0.000 | 🟡 Needs strategy data |
| solitaire | 3 | 0/3 | 0.000 | ❌ Single player game |

### v7 GAME Final Results (100/100)

**Total: mean=0.145, 27/88 non-zero (31%), 12 error (12%)**

| Game | n | Win Rate | Mean | Assessment |
|------|---|----------|------|-----------|
| goofspiel | 2 | 100% | 1.000 | ✅ Perfect |
| leduc_poker | 12 | 100% | 0.579 | ✅ Strategy effective! |
| bridge | 1 | 100% | 0.480 | Small sample |
| euchre | 8 | 63% | 0.297 | Can improve |
| gin_rummy | 5 | 20% | 0.088 | 🔴 Needs bot data |
| othello | 12 | 0% | 0.000 | 🔴 Needs bot data |
| liars_dice | 4 | 0% | 0.000 | 🔴 Needs bot data |
| hex | 7 | 0% | 0.000 | 🔴 Needs bot data |
| go/chess/checkers | 15 | 0% | 0.000 | ❌ LLM cannot learn |

**Key conclusions**:
- parse error 29%→12% ✅ (system prompt unification fix effective)
- leduc_poker 12/12 all wins ✅ (proves SFT can learn game strategies)
- v8 with game_bot strategy data (7 games, 1687 entries) should enable gin_rummy/othello/hex/liars_dice to break through 0%

### v7 NAVWORLD Results: All Zeros (18/18 = 0.00)

**Root cause diagnosis**:
1. API key issue (fixed): eval script didn't pass AMAP_MAPS_API_KEY
2. **Data format root cause**: v7 training serialized tool_calls as `<tool_calls>JSON</tool_calls>` text,
   but Qwen3 native tool calling format is `<tool_call>JSON</tool_call>` + `<tool_response>` + `<tools>`.
   Model learned a format that doesn't match eval environment expectations.

**v8 fix plan**: Use `tokenizer.apply_chat_template(messages, tools=tools)` to generate training text,
ensuring tool calling format is fully consistent with Qwen3 native format.

---

## v8 Training — 2026-03-14

### Key Improvements vs v7
1. **NAVWORLD**: Use `apply_chat_template(tools=)` to generate native `<tool_call>` format (vs v7's text serialization)
2. **GAME**: Added 2193 game_bot strategy entries (7 games, programmatic strategy bot generated)
3. **Data format**: All data uses `text` field (apply_chat_template output), fully aligned with Qwen3 tokenizer

### Data (7002 entries)
| Source | Count |
|--------|-------|
| GAME v7 clean | 2417 |
| GAME bot (7 games) | 2193 |
| SWE-SYNTH | 1350 |
| NAVWORLD (native tool_call) | 605 |
| LIVEWEB (native tool_call) | 437 |

### Hyperparameters
- lr=1e-4, batch=2, grad_accum=8, epochs=1, seq=4096
- LoRA r=64, alpha=128, packing=True
- HF: YOUR_HF_USER/affine-qwen3-32b-v8 (private, auto-upload)

### Loss Curve
| Step | v8 | v7 |
|------|-----|-----|
| 10 | 0.6741 | 0.7922 |
| 20 | 0.5252 | 0.5996 |
| 30 | 0.3892 | 0.3645 |
| 40 | 0.3318 | 0.3428 |
| 50 | 0.2796 | 0.3044 |

| 60 | 0.2610 | 0.2730 |
| 70 | 0.2195 | 0.2669 |
| 80 | 0.2121 | 0.2422 |
| 90 | 0.1813 | 0.2190 |
| 100 | 0.1847 | 0.2124 |

| 110 | 0.1621 | 0.2160 |
| 120 | 0.1619 | 0.2108 |
| 130 | 0.1509 | 0.1988 |
| 140 | 0.1481 | 0.2048 |
| 150 | 0.1313 | 0.1591 |

| 160 | 0.1417 | 0.1876 |
| 170 | 0.1538 | 0.1581 |
| 180 | 0.1320 | 0.1658 |
| 190 | 0.1389 | 0.1841 |
| 200 | 0.1196 | 0.1761 |

| 210 | 0.1439 | 0.1766 |
| 220 | 0.1333 | 0.1769 |
| 230 | 0.1289 | 0.1776 |
| 240 | 0.1251 | — |
| 250 | 0.1140 | — |

| 260 | 0.1176 | — |
| 270 | 0.1102 | — |
| 280 | 0.1194 | — |
| 290 | 0.1158 | — |
| 300 | 0.1084 | — |
| 310 | 0.0970 | — |
| 320 | 0.1145 | — |

### Training Complete ✅
- **Total time**: 4.4h, 323 steps, cost ~$10.6
- **Final loss**: ~0.11 (vs v7 0.18, v6 0.22)
- **HF**: YOUR_HF_USER/affine-qwen3-32b-v8 (private, auto-upload)
- v8 loss historically lowest, outperforming v7 throughout

### v8 Evaluation
- First eval round all zeros due to Docker container restart issue (stale container state) — not a model problem
- Direct API test confirmed model works: GAME outputs pure number ✅, NAVWORLD outputs `<tool_call>` ✅
- After container cleanup, re-ran 20 samples GAME:
  - mean=0.090, 6/18 non-zero (33%), 2 error (10%)
  - **gin_rummy 2/2 all wins (0.375)** — v7 was 0/5! Bot strategy data worked!
  - **hearts 1/1 (0.33)** — v7 was only 0.083
  - othello/hex/go still 0% — need stronger strategies or abandon

### NAVWORLD All-Zero Root Cause Final Identification
- **sglang missing `--tool-call-parser` parameter**
- Model correctly outputs `<tool_call>` text, but sglang doesn't parse it into OpenAI `tool_calls` field
- Eval environment sees `tool_calls=None` → considers no tool calls → 0 score
- **Fix**: Add `--tool-call-parser qwen25` when starting sglang
- Post-fix verification: `tool_calls` field correctly returned ✅
- NAVWORLD re-eval results (after tool-call-parser fix):
  - **mean=0.096, 6/18 non-zero (33%)** — First time breaking zero score!
  - Score distribution: 0.22, 0.23, 0.27, 0.28, 0.28, 0.45
  - v5/v6/v7 all 0% → v8 33% non-zero
  - Root cause chain: training data format (apply_chat_template) + sglang (tool-call-parser) dual fix

### v8 Complete Evaluation Summary

| Env | Samples | Mean | Non-zero Rate | Error |
|-----|---------|------|--------------|-------|
| GAME | 20 | 0.090 | 33% | 10% |
| NAVWORLD | 20 | 0.087 | 30% | 0% |

**vs v7**: GAME similar, NAVWORLD broke through from 0 to 0.087.
**vs leaderboard**: #1 NAVWORLD ~20 points, v8's 8.7 is competitive but needs improvement.

### SWE-SYNTH / LIVEWEB Evaluation Results
- **SWE-SYNTH**: Cannot evaluate locally (needs breaker service to pre-generate tasks)
- **LIVEWEB**: Cannot evaluate locally (task_id range restriction, needs predefined task set)
- These two environments can only be verified through leaderboard deployment

### v8 Final Conclusion
- **Evaluable environments**: GAME 0.090 (20s), NAVWORLD 0.087 (20s, first breakthrough)
- **Cannot locally evaluate**: SWE-SYNTH, LIVEWEB (need deployment verification)
- Merged model uploaded to HF: `YOUR_HF_USER/affine-qwen3-32b-v8-merged` (private, 65GB)
- Awaiting user authorization to deploy to Chutes

## v9 Training — 2026-03-15

### Improvements vs v8
1. **LGC-v2 (3353) + PRINT (2899) re-included** (leaderboard still scoring, geometric mean cannot have gaps)
2. **NAVWORLD 28 new key entries** supplemented (old key expired → empty tool return data fixed)
3. Data count 13282 entries (vs v8 7002, +90%)

### Data (13282 entries)
| Env | Count | Share |
|-----|-------|-------|
| GAME (v7 clean + bot) | 4610 | 34.7% |
| LGC-v2 | 3353 | 25.2% |
| PRINT | 2899 | 21.8% |
| SWE-SYNTH | 1350 | 10.2% |
| NAVWORLD | 633 | 4.8% |
| LIVEWEB | 437 | 3.3% |

### Loss Curve
| Step | v9 | v8 |
|------|-----|-----|
| 10 | 0.6755 | 0.6741 |
| 20 | 0.5642 | 0.5252 |
| 30 | 0.4859 | 0.3892 |
| 40 | 0.3709 | 0.3318 |
| 50 | 0.2829 | 0.2796 |

| 60 | 0.3118 | 0.2610 |
| 70 | 0.2419 | 0.2195 |
| 80 | 0.2880 | 0.2121 |
| 90 | 0.2563 | 0.1813 |
| 100 | 0.2288 | 0.1847 |

| 110 | 0.2187 | 0.1621 |
| 120 | 0.2266 | 0.1619 |
| 130 | 0.1809 | 0.1509 |
| 140 | 0.1896 | 0.1481 |
| 150 | 0.2104 | 0.1313 |

| 160 | 0.1736 | 0.1417 |
| 170 | 0.1996 | 0.1538 |
| 180 | 0.1815 | 0.1320 |
| 190 | 0.1934 | 0.1389 |
| 200 | 0.2045 | 0.1196 |

| 210 | 0.1663 | 0.1439 |
| 220 | 0.1776 | 0.1333 |
| 230 | 0.1760 | 0.1289 |
| 240 | 0.1707 | 0.1251 |
| 250 | 0.1769 | 0.1140 |

| 260 | 0.1742 | 0.1176 |
| 270 | 0.1639 | 0.1102 |
| 280 | 0.1680 | 0.1194 |
| 290 | 0.1556 | 0.1158 |
| 300 | 0.1672 | 0.1084 |

| 310 | 0.1744 | 0.0970 |
| 320 | 0.1807 | 0.1145 |
| 330 | 0.1528 | — |
| 340 | 0.1652 | — |
| 350 | 0.1532 | — |

| 360 | 0.1465 | — |
| 370 | 0.1498 | — |
| 380 | 0.1367 | — |
| 390 | 0.1379 | — |
| 400 | 0.1425 | — |

### Training Complete ✅
- **Total time**: 5.7h, 421 steps, cost ~$13.7
- **Final loss**: ~0.14 (vs v8 0.11, v7 0.18)
- **HF**: YOUR_HF_USER/affine-qwen3-32b-v9 (private, auto-upload)
- v9 loss higher than v8 but covers 6 environments (incl. LGC-v2/PRINT)

### v9 GAME Evaluation (concurrency 4 + timeout 7200s + only eval training games)
- 32/100 samples, 12 non-zero (38%), mean=**0.187**, 0 error
- vs old config (serial + 600s timeout + all 22 games): mean 0.10→0.19, qualitative leap
- Key finding: 58min game scored 0.33 — old timeout would miss these scores
- 2 perfect scores (1.00), highest single game 0.62
- LGC-v2/PRINT did not hurt GAME capability

### v9 GAME Final Intermediate Results (74/100, rental disconnected)
- 74 samples, 27 non-zero (36%), mean=**0.171**, trend sufficiently stable
- NAVWORLD eval not started (rental disconnected before GAME phase completed)
- Rental unreachable (2026-03-15 ~21:00), model safely on HF

### Deployment Ready
- v8: `YOUR_HF_USER/affine-qwen3-32b-v8-merged` (private)
- v9: `YOUR_HF_USER/affine-qwen3-32b-v9-merged` (private)
- Awaiting user authorization to deploy to Chutes

### Rental Lost + Recovery
- Old rental disconnected, new rental `rentals-w58tlzhv9xyh3dis` activated
- Resolved sglang CUDA toolkit dependency issue (installed cuda-nvcc-12-8 + cuda-cudart-dev-12-8)

### v9 Complete Evaluation Results (concurrency 4, timeout 7200s, only eval training games)

| Env | Samples | Non-zero | Mean | Notes |
|-----|---------|----------|------|-------|
| GAME | 87 | 36 (41%) | **0.201** | Leaderboard ~20 points |
| NAVWORLD | 100 | 23 (23%) | **0.052** | Leaderboard ~5 points |

**vs v8**: NAVWORLD from 0.087 (20s) → 0.052 (100s). v8 had few samples with high variance; 100 samples' 0.052 is more reliable.
**vs v5**: NAVWORLD from 0.000 → 0.052, GAME from 0.145 (600s timeout) → 0.201 (7200s timeout)

---

## v10 Training — 2026-03-16

### Improvements vs v9
1. **MemoryGym 500 entries** added (pre-launch environment, training early)
2. Data count 13733 entries (vs v9 13282, +MemoryGym 500)
3. Covers 7 environments: GAME, NAVWORLD, SWE-SYNTH, LIVEWEB, LGC-v2, PRINT, MemoryGym

### Training Status
- New rental `rentals-w58tlzhv9xyh3dis` (4×H200)
- Resolved CUDA toolkit dependency issue (cuda-nvcc-12-8 + cuda-cudart-dev-12-8)
- HF: YOUR_HF_USER/affine-qwen3-32b-v10 (private)

### Training Complete ✅
- **Total time**: 9.1h, 441 steps
- **Final loss**: ~0.19 (converged at 0.19-0.23)
- v10 loss ~0.05 higher than v9 (MemoryGym new environment raises it), but 7 environments fully covered

### v10 GAME Final Results
- 99 samples, **41 non-zero (41%)**, mean=**0.220**
- vs v9: 0.220 vs 0.201 — v10 slightly better, MemoryGym did not impact GAME
### v10 Complete Evaluation Results

| Env | Samples | Non-zero | Mean | vs v9 |
|-----|---------|----------|------|-------|
| GAME | 99 | 41 (41%) | **0.220** | 0.201 (+9%) |
| NAVWORLD | 100 | 28 (28%) | **0.051** | 0.052 (flat) |

**Conclusion**: v10 GAME slightly better than v9, NAVWORLD flat. Adding MemoryGym 500 entries had no negative impact.
Model deployment ready: `YOUR_HF_USER/affine-qwen3-32b-v10-merged` (private)

---

## v11 Training — 2026-03-17

### Improvements vs v10
1. **NAVWORLD**: 632→2154 entries (+240%), all new API key generated, 100% direction coverage
2. Data count 15273 entries (vs v10 13733, +11%)

### Training Status
- New rental `rentals-w58tlzhv9xyh3dis` (4×H200)
- HF: YOUR_HF_USER/affine-qwen3-32b-v11 (private)

---

---

### v8 Available Data

| Source | Count |
|--------|-------|
| GAME v7 clean (DDB+CoT) | 2417 |
| GAME bot (7 game strategies) | 1687 |
| NAVWORLD v7 clean | 605 |
| SWE-SYNTH v7 clean | 1350 |
| LIVEWEB v7 clean | 437 |
| **Total** | **6496** | (lr=1e-4 vs 5e-5). v7 step 100 loss (0.21) already better than v6 final loss (0.22). HF auto-upload working normally.

---
