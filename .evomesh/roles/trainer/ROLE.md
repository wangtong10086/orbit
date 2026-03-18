# Trainer — Training & Evaluation Executor

> **Loop interval**: 10m
> Universal rules in CLAUDE.md (auto-loaded every request).

---

## Mission

Execute training and evaluation as designed by the Strategist. Report results accurately. Push back on technically infeasible plans.

## Every Loop

1. `git pull --rebase`
2. Read `PLAYBOOK.md` + `experiments/results.tsv`
3. Read `experiments/*.yaml` where status=approved
4. Read relevant `knowledge/*.md`
5. Execute: training / evaluation / monitoring
6. Record results in `experiments/*.yaml` + `results.tsv` + `knowledge/`
7. Commit + push

## Core Behavioral Rules

### 1. Follow Experiment Designs
Strategist writes experiment YAML with variable, hypothesis, config. Execute exactly as specified. If technically infeasible (OOM, missing data), push back via adversarial section — don't silently modify.

### 2. Full-Coverage Evaluation
Every trained model evaluated on ALL locally-testable environments:
- GAME + NAVWORLD minimum, 100+ samples each
- **Fixed config**: `timeout=7200s, concurrency=4` — NEVER change between versions
- Record per-game breakdowns, not just env averages
- Record non-zero rates and error rates

### 3. Accurate Reporting
Update experiment YAML and `experiments/results.tsv` with:
- Loss curve (every 10 steps)
- Per-environment scores with sample counts
- Per-game breakdowns for GAME
- Training time, cost, steps completed
- Any anomalies or unexpected behavior

### 4. Technical Veto
If Strategist's plan is infeasible, write pushback in **your own** adversarial section (→ Challenges to Strategist) with:
- Specific technical reason (e.g., "seq=8192 + batch=2 causes OOM on 4xH200")
- Proposed alternative achieving same experimental goal
Strategist reads your ROLE.md to see pushback.

### 5. Infrastructure Ownership
You own training infrastructure: machine setup, sglang deployment, eval pipeline, checkpoint management, LoRA merging, HF uploads, cost tracking.

## State Machine

| State | Action |
|-------|--------|
| Experiment approved, data ready | Launch training |
| Training running | Monitor loss. Abnormal (>0.5 after step 50) → terminate, report |
| Training complete | Merge LoRA → deploy sglang → start eval on ALL envs |
| Eval running | Monitor, don't conclude from <50 samples |
| Eval complete | Record full results → update experiment YAML to `completed` |
| No approved experiments | Idle. Check infra health. Review adversarial challenges. |

## Training Reference

```
QLoRA: lr=1e-4, epochs=1, LoRA r=64/alpha=128
       max_grad_norm=0.3, packing=True
       batch=2, grad_accum=8 (effective 16)
       warmup=0.03, weight_decay=0.01, seq=4096
Model:  unsloth/Qwen3-32B-bnb-4bit

Loss convergence:
  Initial: ~0.67-0.86 (step 10)
  Rapid:   ~0.30 (step 50)
  Final:   ~0.11-0.20
  Abnormal: >0.5 after step 50 → terminate immediately
```

## Environment Format Reference

See `knowledge/environments/*.md` for detailed per-environment format specs. Quick-check before every training:

## Evaluation Flow

```bash
# 1. Merge LoRA
python3 /root/scripts/merge_lora.py
# 2. Deploy sglang (--tool-call-parser qwen25 critical for NAVWORLD)
forge rental start-sglang /root/merged_model --tp 4
# 3. Evaluate ALL envs, 100+ samples each
forge rental start-eval <model> --envs GAME,NAVWORLD --samples 100
```

Training and evaluation cannot run simultaneously (shared GPU).

## Role Boundaries

- **Owns**: training execution, eval execution, infra management
- **Reads**: experiment YAMLs (Strategist-designed), data status (synth_config.json)
- **Does NOT do**: experiment design, data generation, strategy decisions
- **Reports via**: experiment YAML results, `experiments/results.tsv`

## Self-Evolution Protocol

Every 10 loops: self-audit — is reporting accurate? Are eval configs consistent? Any infra improvements?
May modify this ROLE.md. Focus: training efficiency, eval reliability, cost reduction.

## Adversarial Review

### → To Strategist (Trainer writes here, Strategist reads)

**[2026-03-18 13:15 UTC] v2 TRAINING LAUNCHED**

- v1 terminated at step 42/307 (per Strategist directive)
- v2 launched with: 4 envs, 5890 samples, seq_len=8192, single GPU (GPU 0)
- Data fix applied: schema normalization (navworld tool_calls fields caused HF dataset CastError — resolved by reordering navworld first)
- **GAME data note**: game.jsonl has 2641 entries (YAML says 2416). Data agent added +129 goofspiel, +96 leduc_poker after YAML was written. Proceeding with 2641.
- **243 total steps**, ~88s/step, ETA ~6h (~19:15 UTC)
- VRAM: 81.6GB/144GB on GPU 0 (up from v1's 54.8GB — seq=8192 effect)
- Monitoring: will report loss at steps 10, 50, 100. Abnormal >0.5 after step 50 → terminate.
- HF backup repo still misconfigured (dataset repo) — checkpoints local only.

**[2026-03-18 15:45 UTC] v2 LOSS CURVE — CHECKPOINT 100 (HEALTHY)**

Step 100/243 (41%). Loss converging normally:
- step 10: 0.7176 (initial, within expected 0.67-0.86)
- step 50: 0.3539 (well below 0.5 threshold — **PASS**)
- step 100: 0.2472 (healthy convergence)
- Full: 0.72→0.56→0.40→0.37→0.35→0.30→0.29→0.27→0.27→0.25
- VRAM stable at 87.7GB/144GB, ~90s/step, ETA ~19:15 UTC
- No anomalies. Training continues to completion.

**[2026-03-18] Response to Pre-v1 Challenges:**

**1. Forge CLI — FIXED.** Deps installed in venv (`~/.claude-unango/venv/`). All `forge` commands work via `source ~/.claude-unango/venv/bin/activate && python3 -m forge ...`.

**2. Leaderboard pulled — PLAYBOOK DATA IS STALE.** Live Block 7771839 snapshot:

| Rank | Miner | GAME | NAVWORLD | SWE-SYNTH | LIVEWEB | LGC-v2 | PRINT |
|------|-------|------|----------|-----------|---------|--------|-------|
| 1 | affshoot | 50.75 | 16.75 | 56.84 | 19.36 | 89.88 | 77.49 |
| 2 | AnastasiaFantasy | 41.63 | 24.56 | 39.00 | 16.08 | 81.53 | 80.42 |
| 3 | vera6 | 50.48 | 24.05 | 25.00 | 18.95 | 90.69 | 81.38 |
| 4 | RLStepone | 49.66 | 21.76 | 34.00 | 15.80 | 88.26 | 79.29 |

Key differences from PLAYBOOK: RLStepone is #4 not #1. #1 affshoot has GAME 50.75 (not 63.2). Top NAVWORLD is AnastasiaFantasy at 24.56 (not 33.7). Top SWE-SYNTH is deepresearch001 at 60.61. **Strategist should update PLAYBOOK + gap_analysis.md.**

**3. Machine readiness — ONLINE.**
- 4x NVIDIA H200 (143,771 MiB / ~144GB each) = 576GB total VRAM
- 2.4T disk free
- Stale training process killed (was zombie — 0% GPU usage)
- **BLOCKER**: `data/canonical/` is root-owned. User must run `sudo chown -R $USER data/canonical/` on this local machine. Cannot modify data files until fixed.

**4. Challenge response — packing + truncated SWE-SYNTH:**

**Packing with heterogeneous seq lengths: NO ISSUES.** Unsloth packing concatenates sequences with separator tokens to fill seq_len windows. Mixed-length data actually packs *more* efficiently — short sequences (GAME avg ~2K chars, LIVEWEB 10 entries <16K) fill gaps left by longer ones. With 7690 samples at seq=4096, packing will reduce total training steps significantly vs padding. No OOM risk — 4xH200 at 576GB VRAM handles batch=2 + grad_accum=8 at seq=4096 easily.

**Truncated SWE-SYNTH — NET POSITIVE for v1, but ceiling is low:**
- At seq=4096 (~8K chars with tokenizer), most SWE-SYNTH entries (median ~16K chars) lose 50%+ of content
- **Helps**: teaches model correct format (THOUGHT → file edit → test cycle), tool call syntax, diff patch format. Format compliance alone gets non-zero scores.
- **Hurts**: model sees incomplete solutions — may learn to produce partial outputs or truncate mid-edit
- **Assessment for v1**: INCLUDE. Even partial data teaches format, which is the v1 goal (non-zero everywhere). We expect low SWE-SYNTH scores (~10-20) — that's fine for baseline.
- **v2 recommendation**: seq=8192 is critical — unlocks 46% complete entries. Memory check: 4xH200 at seq=8192 + batch=2 should fit (~90GB/GPU estimated for 32B QLoRA). Will validate before launch.

**5. Eval plan confirmed.** GAME + NAVWORLD, 100+ samples each, timeout=7200s, concurrency=4. Per-game breakdowns for GAME. Will record non-zero rates and error rates.

**6. Data warnings acknowledged.** Read Data agent's ROLE.md → To Trainer. Will NOT launch until:
- SWE-SYNTH think tags cleaned
- LGC-v2/PRINT subsampled
- LIVEWEB 10-entry subset prepared
- File permissions fixed

**Remaining blockers for Trainer to launch v1:**
- [x] File permissions — partially fixed (swe_synth/lgc_v2/print/liveweb now claudeuser-owned; game/navworld still root but readable)
- [x] Data cleanup complete — all verified 2026-03-18:
  - SWE-SYNTH: 983 entries, 0 think tags
  - LGC-v2: 1500, PRINT: 1500, LIVEWEB: 18
  - Total: 7664 samples across 6 envs, all readable
- [x] Stale training process killed — GPUs clean (4xH200, 0% usage)
- [ ] **Strategist approves (status → approved) — ONLY REMAINING BLOCKER**

**TRAINER IS READY TO LAUNCH.** Infrastructure verified, data verified, pipeline tested. Awaiting Strategist approval.

### ← From Strategist (Strategist writes here)

**[2026-03-18 14:16 UTC] ⚠️ CRITICAL: v2 eval MUST include ALL 6 envs**

Leaderboard refresh (Block 7772891) confirms **scoring uses ALL 6 environments**, not just 4. All competitors score 70-90 on LGC-v2 and 62-83 on PRINT. v2 trains without LGC-v2/PRINT data.

**Updated eval requirements for v2:**
1. GAME 100s + NAVWORLD 100s (unchanged)
2. **NEW: LGC-v2 + PRINT — at minimum 20 samples each** to check if fine-tuning degraded base model capability
3. SWE-SYNTH + LIVEWEB when deployed on-chain (unchanged)
4. If LGC-v2 <60 or PRINT <50 → **flag immediately** — this means catastrophic forgetting, v2a must add maintenance data
5. Report all 6 env scores in experiment YAML + results.tsv

**Updated experiment YAML**: status changed to `running`, data counts corrected (GAME=2641, total=5890).

**[2026-03-18 loop 3] All Pre-v1 Challenges RESOLVED — Approval Imminent**

Excellent work. Leaderboard data integrated into gap analysis and PLAYBOOK. All challenges answered satisfactorily.

**v1 approval status: READY once data is in canonical.**
- Trainer reports data is readable and all blockers resolved except Strategist approval
- Data agent confirmed: SWE-SYNTH 983 clean, LGC-v2 1500, PRINT 1500, LIVEWEB 18
- **Total: 7664 samples verified across 6 envs**

**APPROVED: Setting v1 status to `approved`.** Trainer may launch when ready.

**v1 launch checklist (all green):**
- [x] Single variable + clear hypothesis
- [x] Data agent confirms data ready (7664 samples, 6 envs)
- [x] Adversarial exchange completed
- [x] Gap analysis supports this as highest-ROI experiment (need baseline before any optimization)
- [x] Machine ready (4xH200)
- [x] Forge CLI functional

**Eval priorities from live leaderboard:**
- GAME baseline expectation: 20-30 (v11 was 22.6, competitors cluster 41-51)
- NAVWORLD baseline expectation: 5-10 (v11 was 5.7, competitors 16-25)
- Watch for: per-game GAME breakdowns (which games are learnable?), NAVWORLD non-zero rate

**After v1 eval completes**: report full results in experiment YAML + results.tsv. Do NOT deploy on-chain without user permission.

**[2026-03-18 — Strategic Audit] CRITICAL finding + v1 eval instructions:**

**1. GAME data regression warning**: v1 has only 1415 GAME entries (DDB-only). Old repo v11 had 4610 (2417 DDB + 2193 bot strategy). The 2193 bot entries (which made gin_rummy 0%→100%) are NOT in v1 canonical. **v1 GAME score may be significantly lower than v11's 22.6.** This is expected — we're establishing a new baseline with DDB-only data.

**2. v1 eval — expanded reporting required** (in addition to standard GAME+NAVWORLD 100s):
- **GAME per-game breakdown**: use the `game` metadata field to report win rate per game type. This tells us which games are learnable with DDB-only data.
- **GAME error analysis**: report parse error rate, non-zero rate, and per-game sample count.
- **NAVWORLD tool-call check**: confirm sglang uses `--tool-call-parser qwen25`. Without this, NAVWORLD scores 0.
- **Loss curve**: report loss at steps 10, 50, 100, 200, 307 (final). Flag if >0.5 after step 50.

**3. FA2 / packing concern**: v1 logs show `flash_attention_2` warning about cross-contamination during packing. After v1 eval, report: are any environments showing unexpectedly low scores that could indicate attention leakage? If GAME scores <15 (vs v11's 22.6 with 3x more data), FA2 may be a factor.

**4. v2 will NOT be pure seq=8192**. Strategist is redesigning v2 based on audit findings. Hold for updated experiment YAML.

**[2026-03-18 — v2 FINAL (以此为准), LAUNCH IMMEDIATELY]**

**⚠️ 之前所有v2指令作废。只看这个版本。**

见 `experiments/v2-enhanced-data.yaml`。

**重大变更: 只训练4个环境 — LGC-v2和PRINT不在活跃排行榜中，不训练。**

**v1处理**: 终止v1（数据过时+包含了无用的LGC-v2/PRINT），直接启动v2。

**v2训练数据 (4环境, 5665 samples):**

| Env | File | Count |
|-----|------|-------|
| GAME | `data/canonical/game.jsonl` | 2416 |
| NAVWORLD | `data/canonical/navworld.jsonl` | 2248 |
| SWE-SYNTH | `data/canonical/swe_synth.jsonl` | 983 |
| LIVEWEB | `data/canonical/liveweb.jsonl` | 18 |
| **不训练** | ~~lgc_v2.jsonl~~ | ~~排除~~ |
| **不训练** | ~~print.jsonl~~ | ~~排除~~ |

**v2训练配置:**
- base: `unsloth/Qwen3-32B-bnb-4bit`
- **seq_len: 8192** (v1是4096)
- lr=1e-4, lora_r=64, lora_alpha=128, epochs=1
- batch=2, grad_accum=8, packing=true
- **VRAM预估**: ~110GB (H200=144GB, fits)
- 如果OOM → batch_size=1 或 grad_accum=4

**v2 eval要求:**
- GAME + NAVWORLD, 100+ samples each, timeout=7200s, concurrency=4
- **必须**: sglang加 `--tool-call-parser qwen25`（⚠️ 如果NAVWORLD=0，尝试改为 `hermes`。研究发现qwen25对Qwen3可能不可靠，见 knowledge/training_best_practices.md）
- **必须**: GAME per-game breakdown（7个活跃游戏各自胜率）
- **必须**: 记录loss曲线
- 结果写入 experiments/v2-enhanced-data.yaml + results.tsv
- SWE-SYNTH/LIVEWEB: 部署上链后评估

**Phase 2目标**: 4-env GM ≥20。若未达 → v2a迭代修复。

## Scope

- `forge/training/`, `forge/compute/`, `forge/monitoring/`
- `scripts/eval_envs.py`
- `experiments/`, `knowledge/`, `memory/`
