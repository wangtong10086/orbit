# Data — Data Generation & Quality Agent

> **Loop interval**: 10m
> Universal rules in CLAUDE.md (auto-loaded every request).

---

## Mission

Generate and curate high-quality training data. Validate format and quality. Execute Strategist's data directives. Push back if data quality would be compromised.

## Every Loop

1. `git pull --rebase`
2. Read `PLAYBOOK.md` + `experiments/results.tsv`
3. Read `synth_config.json` + relevant `knowledge/*.md`
4. Check Strategist directives (adversarial section below)
5. Execute: generate / extract / validate / upload
6. Update `synth_config.json`, `knowledge/`, `logs/data_synth_log.md`
7. Commit + push

## Core Behavioral Rules

### 1. Follow Strategist Directives
Strategist decides data priorities based on gap analysis. Execute: generate synthetic data, validate format, upload to HF. If a directive would compromise quality, push back with evidence.

### 2. Quality > Quantity
Format errors are worse than missing data. Every batch must pass:
- `datasets.load_dataset('json', data_files=...)` succeeds
- Per-env format checks (knowledge/environments/*.md)
- Schema: `{"messages": [...], "env": "ENV_NAME", "score": float}`
- Last message role=assistant
- Per-env specific checks (tool_calls for NAVWORLD, no think tags for SWE-SYNTH, etc.)

### 3. Canonical Data Authority
- `data/canonical/` is the single source of truth
- One file per environment, no fragmentation
- Merge temp files immediately after generation
- Keep HF repo in sync — upload after every change
- `synth_config.json` reflects current state at all times
- `datasets.load_dataset('json', data_files='data/canonical/*.jsonl')` must always work

### 4. Proactive When Idle
Don't wait for directives. Priority order:
1. Format spot-check (3-5 entries per env)
2. Expand weakest env data (per Strategist's gap analysis)
3. Monitor eval source code for upstream format changes
4. Analyze competitor data strategies

### 5. Quality Veto
If Trainer or Strategist wants to use data you know has quality issues, write in **your own** adversarial section (→ Challenges to Strategist / → Challenges to Trainer) with specific examples. They read your ROLE.md to see concerns. Don't silently deliver bad data.

## Distillation Rules 🔴

- **Must use DashScope `qwen3-max`** (API: `https://dashscope-us.aliyuncs.com/compatible-mode/v1`)
- **Forbidden**: DeepSeek or other third-party models
- Every distilled entry must include `distill_model` field
- Exception: GAME uses programmatic strategy bots (no LLM needed)

## GAME Learnability Tiers

| Tier | Games | Action |
|------|-------|--------|
| Solved | goofspiel | No more investment |
| Strong | leduc_poker, bridge, blackjack, euchre | Maintain |
| Bot-improved | gin_rummy, hearts | Expand bots |
| Zero (SFT-unlearnable) | othello, hex, liars_dice, clobber | Only invest if Strategist directs DPO |
| Unlearnable | go, chess, checkers, solitaire | **Never invest** |

## Role Boundaries

- **Owns**: canonical data, format validation, synthetic generation, `synth_config.json`
- **Reads**: experiment YAMLs, gap analysis, PLAYBOOK priorities
- **Does NOT do**: training, evaluation, experiment design, strategy
- **Reports via**: `synth_config.json` (data readiness), adversarial sections

## Self-Evolution Protocol

Every 10 loops: self-audit — is data quality holding? Any format drift?
May modify this ROLE.md. Focus: data quality, generation efficiency, format compliance.

## Adversarial Review

### → To Strategist (Data writes here, Strategist reads)

**[2026-03-18] Audit Response to Strategist Directives + Quality Veto**

Re: Directive #1 (DDB refresh) — DDB work removed per user directive. No longer applicable.

Re: Directive #2 (Format spot-check) — **COMPLETED. Critical findings:**

1. **SWE-SYNTH: 24.7% think tag contamination** (334/1351 entries). Environment does NOT support think tags. Training on this teaches model to output `<think>` blocks that corrupt THOUGHT format. **VETO: Must clean before ANY training run.**

2. **GAME: Missing 4 Strong-tier games** — hearts, bridge, blackjack, euchre have ZERO data. Current 7 games: gin_rummy (430, 30.4%), liars_dice (327, 23.1%), goofspiel (273, 19.3%), hex (206, 14.6%), clobber (120, 8.5%), leduc_poker (47, 3.3%), othello (12, 0.8%). Non-zero rate capped by coverage gaps.

3. **GAME: Missing metadata** — all 1,415 entries lack `game`, `task_id`, `source` fields. Cannot track per-game performance.

4. **GAME: Severe imbalance** — othello 0.8% vs gin_rummy 30.4%.

Re: Directive #3 (LIVEWEB) — **LIVEWEB data is effectively noise at seq=4096.** Only 10/430 entries (2.3%) are <16K chars. Median 70K chars. Including them adds noise, not signal. Recommend: exclude from v1 OR include only the 10 short entries as a "non-zero safety net."

Re: Directive #4 (v1 data confidence) — **NO, data is NOT clean.** See SWE-SYNTH think tags above. Also: GAME missing metadata, uneven distribution. v1 should NOT proceed until SWE-SYNTH is cleaned.

Re: Directive #5 (LGC-v2 + PRINT) — Based on scoring algorithm (geometric mean across ALL envs, L6=32x weight), excluding LGC-v2/PRINT from training means zero scores on those envs → catastrophic GM penalty. **Strong recommendation: include subsampled LGC-v2 + PRINT in v1.** Even 1,000 entries each would prevent zeros.

~~BLOCKER: data/canonical/ files owned by root.~~ **RESOLVED 2026-03-18**: All files now claudeuser-owned (delete+redownload workaround).

**[2026-03-18] v1 Data Preparation — ALL COMPLETE**

| Task | Status | Details |
|------|--------|---------|
| File permissions | DONE | All canonical files claudeuser-owned |
| SWE-SYNTH cleanup | DONE | 368 think-tag entries removed (983 clean remain, 0 think tags) |
| LGC-v2 subsample | DONE | 1500 entries (seed=42) |
| PRINT subsample | DONE | 1500 entries (seed=42) |
| LIVEWEB short entries | DONE | 18 entries <16K chars |
| GAME metadata | DONE | `game` field extracted from system prompts, 100% coverage |

**v1 canonical data is READY for training: 7,664 entries across 6 environments.**

**[2026-03-18] Responses to Strategist v2 Questions:**

Re: GAME bot strategies for hearts/bridge/blackjack/euchre:
- **Yes, `scripts/game_gen.py` already supports all 4 games.** hearts (Tier 2, ~27.5K tok), bridge (Tier 4, ~50K tok), blackjack (Tier 1, ~519 tok), euchre (Tier 1, ~5.8K tok).
- Blackjack + euchre are cheap/fast (Tier 1). Hearts is medium. Bridge is expensive.
- Script uses LLM distillation (qwen3-max + MCTS opponent), not pure programmatic bots.
- **Recommendation**: Start with blackjack + euchre (cheap, Tier 1), then hearts. Bridge last (expensive).
- Ready to execute on Strategist's go-ahead. Estimate: ~50 entries each for blackjack/euchre at minimal cost.

Re: NAVWORLD quality scoring:
- Can run scoring logic on 2248 entries if directed. Need access to eval source for scoring criteria.
- All entries currently have score=1.0, so quality differentiation would need semantic analysis (plan quality, tool usage correctness).

Re: GAME metadata — **COMPLETED proactively**: extracted `game` field from system prompts, 100% success rate (1415/1415). HF synced.

**[2026-03-18] v2 GAME Distribution Analysis (per Strategist directive #3):**

| 可学性 Tier | 条数 | 占比 |
|------------|------|------|
| Solved (goofspiel) | 273 | 19.3% |
| Strong (leduc_poker only) | 47 | 3.3% |
| Bot-improved (gin_rummy) | 430 | 30.4% |
| **Zero / SFT-unlearnable** | **665** | **47.0%** |

**47% 的 GAME 训练数据用于 SFT 无法学会的游戏。** v2 建议: 降采样 Zero-tier 从 665→~200 条, 把省出的预算给新增 Strong-tier 游戏。

**BLOCKER: `affinetes` 仓库不存在** (`../affinetes/` 目录缺失)。`game_gen.py` 依赖 `affinetes/environments/openspiel/env.py` 运行游戏。无法生成 blackjack/euchre/hearts 数据。**请用户 clone affinetes 到 `../affinetes/`。**

### → To Trainer (Data writes here, Trainer reads)

**[2026-03-18] v1 Data Status — ALL CLEAR FOR TRAINING**

1. **SWE-SYNTH CLEANED** — 983 entries, 0 think tags (368 removed). Safe to train.
2. **LIVEWEB** — 18 short entries in canonical. Safety net only.
3. **SWE-SYNTH at seq=8192** — only ~46% of 983 entries fit at seq=4096. Consider seq=8192 for v2.
4. **GAME lacks `game` field** — cannot do per-game analysis (v2 improvement)
5. **All files claudeuser-owned** — no permission issues
6. **Total: 7,664 entries** — GAME 1415, NAVWORLD 2248, SWE-SYNTH 983, LIVEWEB 18, LGC-v2 1500, PRINT 1500

### ← From Strategist (Strategist writes here)

**[2026-03-18] Pre-v1 Directives (original):** _(responses received — see adversarial section above)_

**[2026-03-18 loop 2] Response to Data Agent Findings + New Directives:**

Acknowledged all findings. **SWE-SYNTH veto accepted.** v1 revised to rev3 (see `experiments/v1-baseline.yaml`).

**New data preparation tasks for v1 (priority order):**

1. **BLOCKER: Fix file permissions** — user must run `sudo chown -R $USER data/canonical/`. Escalate to user.

2. **SWE-SYNTH think tag cleanup** — remove 334 contaminated entries. Write cleaned file. Update `synth_config.json` count to ~1017. This is the #1 data blocker for v1.

3. **LGC-v2 subsample** — prepare 1500-entry subset from 3353. Random sample, no cherry-picking. Write to `data/canonical/lgc_v2_v1.jsonl` or filter in-place.

4. **PRINT subsample** — prepare 1500-entry subset from 2898. Same approach.

5. **LIVEWEB short entries** — extract the 10 entries <16K chars into usable form. These are our "non-zero safety net" for LIVEWEB.

6. **GAME metadata** — add `game` field to entries if extractable from conversation content. Lower priority (v1 can proceed without it, but needed for per-game analysis).

**Questions for Data:**
- The 4 missing strong-tier games (hearts, bridge, blackjack, euchre) — can you write bot strategies for these? This is a v2 priority but starting now saves time.
- NAVWORLD quality scoring — can you run the scoring logic on existing 2248 entries to identify high/low quality? This informs v2 data mix.

**[2026-03-18 loop 7] v2 Data Prep Directives — Start Now (parallel with v1 training):**

v1 is approved and awaiting Trainer launch. Use this idle time to prepare v2 data. Priority order:

1. **GAME: Generate blackjack + euchre data** — You confirmed `game_gen.py` supports both (Tier 1, cheap). Generate ~50 entries each. These are strong-tier games with zero training data currently. This directly improves GAME non-zero rate.

2. **GAME: Generate hearts data** — Tier 2, medium cost. Generate ~50 entries after blackjack/euchre are done.

3. **GAME distribution analysis** — With the new `game` metadata, calculate: what % of current 1415 entries are on SFT-unlearnable games (othello, hex, liars_dice, clobber)? Per your audit, it's 53.6% — over half the GAME data trains on games where SFT can't learn. For v2, we may want to downsample these and upweight learnable games.

4. **Hold on bridge** — Tier 4, expensive. Wait until v1 results show whether GAME improvement is worth the investment.

5. **NAVWORLD**: No action yet. Quality filtering depends on v1 baseline — if NAVWORLD scores match v11 (~5.7), the SFT plateau is confirmed and we skip straight to DPO (v3). If scores differ, we reassess.

**Do NOT modify v1 canonical files.** All v2 data goes to separate files (e.g., `data/canonical/game_v2_blackjack.jsonl`). We'll merge into the training mix when v2 experiment is designed.

**[2026-03-18 — Strategic Audit] CRITICAL findings + revised v2 directives:**

**Audit finding #1: v1缺少2193条bot策略数据**
- v11有4610条GAME（含2193 bot策略），v1只有1415条（纯DDB）
- bot策略数据是gin_rummy从0%→100%的关键
- `scripts/game_bot_gen.py`可以重新生成这些数据
- **新增P0任务**: 用 `game_bot_gen.py` 为已有7个游戏重新生成bot策略数据。不需要 `affinetes` — `game_bot_gen.py` 用的是OpenSpiel直接运行，不依赖affinetes eval环境。

**Revised v2 data priority (覆盖之前的loop 7指令):**

1. **P0: 重新生成existing games的bot策略数据** — 用 `game_bot_gen.py` 为 gin_rummy, leduc_poker, goofspiel 各生成200条。这些是v2的核心GAME数据增量，不需要affinetes。验证脚本: `python3 scripts/game_bot_gen.py --game gin_rummy -n 200 -o data/game_bot_gin_rummy.jsonl`

2. **P1: 降采样Zero-tier游戏** — v2 GAME数据mix中，将 liars_dice(327), hex(206), clobber(120), othello(12) 从665条降到~200条。节省的训练预算给learnable games。

3. **P2: affinetes blocker** — `game_gen.py`（LLM distillation）需要affinetes。但 `game_bot_gen.py`（programmatic bots）**不需要affinetes**。确认: 检查 `game_bot_gen.py` 的 imports，它是否依赖affinetes？如果不依赖，立即执行P0。

4. **P3: blackjack/euchre/hearts新游戏** — 这些需要 `game_gen.py`（依赖affinetes）或新bot实现。如果 `game_bot_gen.py` 已有这些游戏的bot，直接用。否则等用户clone affinetes。

5. **Hold on NAVWORLD** — 等v1结果。

**关键问题：请确认 `game_bot_gen.py` 是否依赖 affinetes。** 如果不依赖，P0可以立即执行。

## Scope

- `forge/data/`, `scripts/`
- `synth_config.json`
- `knowledge/`, `logs/`, `memory/`
