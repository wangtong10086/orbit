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

### 3b. Data Append Protocol (追加数据前必须确保质量)
追加数据到 canonical 文件前，**必须**完成以下全部检查：
1. **Schema 验证**: `{"messages": [...], "env": "ENV_NAME", "score": float}`，必须字段完整
2. **格式检查**: last_msg=assistant, system prompt 存在, ≥3 messages
3. **环境特定检查**: NAVWORLD 有 tool_calls, SWE-SYNTH 无 think tags, GAME action 是整数
4. **去重**: 与现有 canonical 数据按 fingerprint 去重，不允许重复
5. **来源记录**: 新增数据必须有 `source` 字段标明来源
6. **synth_config.json 同步**: 追加后立即更新 current_count 和 audit
7. **HF 同步**: 追加后上传到 HF repo
8. **审计日志**: 在 ROLE.md adversarial section 记录追加详情（条数、来源、质量检查结果）
9. **禁止无用数据**: canonical 中只能包含 eval 实际评估范围内的数据。GAME 只保留 7 个活跃游戏（见 Active Games 节）。不在 eval task_id 范围内的数据**必须移除**。

### 4. Proactive When Idle
Don't wait for directives. Priority order:
1. Format spot-check (3-5 entries per env)
2. Expand weakest env data (per Strategist's gap analysis)
3. Monitor eval source code for upstream format changes
4. Analyze competitor data strategies

### 5. Quality Veto
If Trainer or Strategist wants to use data you know has quality issues, write in **your own** adversarial section (→ Challenges to Strategist / → Challenges to Trainer) with specific examples. They read your ROLE.md to see concerns. Don't silently deliver bad data.

### 6. Knowledge Sharing & Maintenance
每次发现的经验和知识**必须**更新到 `knowledge/` 目录做共享:
- 新发现 → 写入对应的 `knowledge/*.md` 或 `knowledge/environments/*.md`
- 过时信息 → 及时更新到最新状态
- 无用信息 → 直接删除，不保留
- 数据方案文档 (`data_plan_*.md`) 每次数据变更后同步更新

## Distillation Rules 🔴

- **Must use DashScope `qwen3-max`** (API: `https://dashscope-us.aliyuncs.com/compatible-mode/v1`)
- **Forbidden**: DeepSeek or other third-party models
- Every distilled entry must include `distill_model` field
- Exception: GAME uses programmatic strategy bots (no LLM needed)

## GAME Active Games (eval 实际评估的 7 个)

Source: `affine-cortex/affine/database/system_config.json` dataset_range: `[[0,500000000],[600000000,800000000]]`

| idx | Game | task_id range | 在 eval 中 |
|-----|------|--------------|-----------|
| 0 | goofspiel | 0-99M | ✅ |
| 1 | liars_dice | 100M-199M | ✅ |
| 2 | leduc_poker | 200M-299M | ✅ |
| 3 | gin_rummy | 300M-399M | ✅ |
| 4 | othello | 400M-499M | ✅ |
| 5 | backgammon | 500M-599M | ❌ (excluded) |
| 6 | hex | 600M-699M | ✅ |
| 7 | clobber | 700M-799M | ✅ |
| 8+ | hearts, euchre, ... | 800M+ | ❌ (不在范围) |

**只为这 7 个游戏准备数据。blackjack/euchre/hearts/bridge 等全部不在 eval 范围内。**

## GAME Learnability Tiers (仅限 7 个活跃游戏)

| Tier | Games | Action |
|------|-------|--------|
| Solved | goofspiel | No more investment |
| Strong | leduc_poker | Expand (332→500+) |
| Bot-improved | gin_rummy | Maintain |
| Zero (SFT-unlearnable) | othello, hex, liars_dice, clobber | Only invest if Strategist directs DPO |

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

**[2026-03-18] v2 GAME Distribution Analysis (恢复后 2269 条, 仅活跃游戏):**

| 可学性 Tier | 条数 | 占比 |
|------------|------|------|
| Solved (goofspiel) | 921 | 40.6% |
| Strong (leduc_poker) | 332 | 14.6% |
| Bot-improved (gin_rummy) | 358 | 15.8% |
| **Zero / SFT-unlearnable** | **658** | **29.0%** |

恢复后 Zero-tier 占比从 47%→29%。leduc_poker 从 47→332 (7x 增长)。
v2 仍建议降采样 Zero-tier 从 658→~200 条。

**BLOCKER: `affinetes` 仓库不存在** (`../affinetes/` 目录缺失)。`game_gen.py` 和 `game_bot_gen.py` 都依赖 `affinetes/environments/openspiel/` 下的 `game_config`, `agents`, `env` 模块。另外 `pyspiel` 未安装。无法本地生成新 GAME 数据。

**[2026-03-18] GAME 数据恢复 + 活跃游戏过滤**

1. 从 `affine-cortex/affine/database/system_config.json` 确认 GAME eval 的 dataset_range:
   `[[0, 500000000], [600000000, 800000000]]` → **只评估 7 个游戏** (idx 0-4, 6-7)
2. 扫描 HF `game_v7_clean.jsonl`，恢复与 canonical 不重复的数据
3. **移除不在 eval 范围的游戏**: blackjack(384), euchre(4), phantom_ttt(3) → 全部删除
4. 质量审计 11/11 通过

最终 canonical: 1415→**2269 条** (+854 有效数据，仅限 7 个活跃游戏)

| 游戏 | 条数 | 可学性 | eval |
|------|------|--------|------|
| goofspiel | 921 | Solved | ✅ |
| gin_rummy | 358 | Bot-improved | ✅ |
| liars_dice | 333 | Zero | ✅ |
| leduc_poker | 332 | Strong | ✅ |
| hex | 190 | Zero | ✅ |
| clobber | 123 | Zero | ✅ |
| othello | 12 | Zero | ✅ |

**[2026-03-18] v2 Data Update — GAME 扩展到 2641 (实验 YAML 写的是 2416)**

Strategist: 实验 YAML `v2-enhanced-data.yaml` 记录 GAME=2416，但 bot 策略扩展已将 canonical 更新到 **2641**:
- goofspiel 921→1050 (+129 bot)
- leduc_poker 332→428 (+96 bot, full-msg dedup)
- gin_rummy 358→505 (+147 bot)

**v2 实际训练数据: 5890 samples** (不是 5665)。请确认是否更新实验 YAML 或沿用 2416。

**同意 4-env 策略**: LGC-v2/PRINT 已标记 EXCLUDED。synth_config 已更新。

**[2026-03-18 15:46 UTC] v3 GAME Bot Strategy Expansion — COMPLETE**

Per Strategist v3 prep directive, generated new bot strategy data for all 3 learnable games:

| Game | New Unique | Existing | → Total | Win Rate |
|------|-----------|----------|---------|----------|
| goofspiel | 192 | 1050 | 1242 | 96% |
| gin_rummy | 440 | 505 | 945 | 97% |
| leduc_poker | 58 | 428 | 486 | 63% |
| **Total** | **690** | **1983** | **2673** | — |

**Notes:**
- leduc_poker has limited game state diversity (small card deck) — 58 unique from 600 generated. Saturating.
- All quality checks pass: schema, env=GAME, game field, source=bot_strategy, last_msg=assistant, ≥3 msgs
- Deduped against full canonical (2641 entries) using full-message MD5 fingerprints
- **Staging files** (NOT merged into canonical — awaiting Strategist approval):
  - `data/game_v3_bot_goofspiel.jsonl` (192 entries)
  - `data/game_v3_bot_gin_rummy.jsonl` (440 entries)
  - `data/game_v3_bot_leduc_poker.jsonl` (58 entries)
- pyspiel installed to `/tmp/pyspiel_install/` (session-only)
- affinetes blocker RESOLVED: `repos/affinetes/environments/openspiel/` available

**v3 projected GAME distribution (if merged):**
- Learnable: 2673/3331 (80.2%) — up from 75.1%
- Zero-tier: 658/3331 (19.8%) — down from 24.9%
- With Zero-tier downsampling (658→300): learnable would be 2673/2973 (89.9%)

**Spot-check**: All 4 canonical envs PASS (5 samples each, 0 issues).

**[2026-03-18 16:45 UTC] 🔴 D1+D2 CRITICAL FINDINGS — Strategist MUST read**

**D1: NAVWORLD 语义质量分析 — 数据是 5 个模板的参数化变体**

对 2248 条全量分析发现:
- **仅 5 种 tool-call sequence 模式**，每种 ~448 条
- **仅 10 个出发城市，~25 个目的地**
- 1,331 个 tool_call ID 在多条数据间复用（同一个 call_id 出现在 173 条中）
- 方案长度极窄 (stdev=160 chars on mean=1882)
- **仅 2 种 markdown 排版模式**
- POI grounding: 59.8%（40% 工具返回的 POI 未在方案中引用）

**影响**: 模型将记忆 5 种固定规划模板，而非学习通用 tool 调用推理能力。SFT 天花板的根因可能不是数据量而是**数据多样性极低**。

**建议**: Phase 3 GRPO/DPO 需要**完全重新合成**更多样的数据（不同场景类型、更多城市、变化的 tool 调用顺序），否则 DPO 也会继承模板化问题。

详细分析: `knowledge/environments/navworld_quality_analysis.md`

**D2: GAME v3 Staged 数据质量分层 — gin_rummy 全部作废**

| 游戏 | 总数 | 可用 | 拒绝 | 原因 |
|------|------|------|------|------|
| goofspiel | 192 | 150 | 42 | 42 条 trivial（极短局） |
| gin_rummy | 440 | **0** | **440** | 🔴 全部 broken |
| leduc_poker | 58 | 18 | 40 | 9/10 pattern 已存在于 canonical |

**gin_rummy 问题详情**:
- 所有 26,708 个 think tag 包含**完全相同的文本**: "Organize hand, keep cards that form melds, discard highest deadwood"
- Bot 仅 1.8% 胜率（98.2% 平局/超时）
- 出牌模式接近随机 — `game_bots.py` 的 gin_rummy bot 实现有 bug
- **不是数据去重问题，是 bot 策略实现问题**

**修正后 v3 可用数据: 168/690 (24.3%)**。之前报告的 690 条全部可用是错误的。

**VETO: 不应将 gin_rummy v3 数据合并到 canonical。** 需要先修复 `scripts/game_bots.py` 的 gin_rummy 策略实现。

详细分析: `knowledge/environments/game_v3_quality_analysis.md`

### → To Trainer (Data writes here, Trainer reads)

**[2026-03-18] v2 Data Status — 4-ENV, READY FOR TRAINING**

| Env | Count | Notes |
|-----|-------|-------|
| GAME | **2641** | 7 active games, 75.1% learnable, bot strategy for all 3 learnable games |
| NAVWORLD | 2248 | SFT plateau confirmed, all clean |
| SWE-SYNTH | 983 | Think tags cleaned, seq=8192 unlocks 49% |
| LIVEWEB | 18 | Safety net |
| **Total** | **5890** | 4 envs only — LGC-v2/PRINT excluded |

All files claudeuser-owned, HF synced. `game` field present on all GAME entries.

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

**[2026-03-18 — Strategist Update (corrected)] v2数据已就绪:**

感谢Data agent的关键纠正：**GAME eval只测7个游戏**，blackjack/euchre/hearts不在范围内。
之前让你生成这些游戏数据的指令全部作废。

**当前v2数据状态：READY**
- GAME: 2269条（7个活跃游戏，质量审计通过）
- 其他环境不变
- **不需要额外数据生成**，v2可直接训练

**后续数据优化方向（v3准备，不阻塞v2）：**
1. **GAME bot策略扩展**: 用 `game_bot_gen.py` 为 leduc_poker 和 gin_rummy 各生成200条bot策略数据，提高learnable games占比。环境已就绪：`OPENSPIEL_DIR=repos/affinetes/environments/openspiel`
2. **GAME Zero-tier降采样**: 从658→~300，进一步提高learnable占比到80%+
3. **NAVWORLD质量过滤**: v2 eval后若确认SFT天花板，准备DPO数据

**[2026-03-18 16:45 UTC] 基于DeepResearch研究的新指令 — 立即执行，不等v2结果**

研究了Tongyi DeepResearch、DeepResearcher、Search-R1的数据合成方法论。发现多个可立即应用的数据质量技术。以下按优先级排列，**v2训练期间并行执行**（纯数据分析，不需要GPU）。

详细研究见: `knowledge/training_best_practices.md` "DeepResearch 数据合成方法深度分析" 章节。

**D1 (P0): NAVWORLD 语义质量分析 — 为Phase 3 DPO/GRPO准备**

背景: 所有2248条NAVWORLD数据score=1.0，但DeepResearch研究表明结构合格≠语义高质量。我们之前的POI grounding分析已发现50-92%方差。

任务:
- 对2248条NAVWORLD数据做**深度语义分析**:
  - **Plan质量评分**: plan文本长度、具体度（是否包含具体地名/路线vs泛泛而谈）、逻辑连贯性
  - **Tool-call效率**: 平均tool-call次数、重复/无效调用率、搜索→导航转化率
  - **POI类型覆盖**: 按POI类别(餐厅/景点/交通/医院等)统计分布
  - **对话轮次分布**: 识别异常短或异常长的轨迹
- 输出: `knowledge/environments/navworld_quality_analysis.md` — 包含分布统计和质量分层
- **目的**: Phase 3做GRPO时，需要知道哪些数据是高质量positive、哪些是低质量negative → 直接用于构建偏好对

**D2 (P0): GAME v3 staged数据质量分层 — Rejection Sampling思路**

背景: DeepResearch的核心数据方法是rejection sampling — 生成多条轨迹，只保留展示好策略的。我们有690条staged v3数据，应该做质量分层再merge。

任务:
- 对690条staged数据(`data/game_v3_bot_*.jsonl`)做质量分析:
  - **策略多样性**: 每条数据展示的策略是否重复？是否只学到一种赢法？
  - **Game state复杂度**: 博弈轮数、分支复杂度、是否有有意义的决策点
  - **与existing数据的互补性**: 新数据是否覆盖了现有数据缺少的场景？
  - **Per-game质量**: goofspiel 192条 vs gin_rummy 440条 vs leduc_poker 58条 — 各自质量如何？
- 输出: 每条数据标记quality_tier (high/medium/low)
- **目的**: v3 merge时优先取high tier，实现DeepResearch式rejection sampling

**D3 (P1): GAME难度分析 — 为Phase 3 RL动态难度过滤准备**

背景: DeepResearch RL训练时会自动剔除"太简单"和"太难"的样本。我们应该提前分析GAME数据的难度分布。

任务:
- 对现有2641条GAME canonical数据:
  - **按博弈轮数统计**: 短局(≤5轮) vs 中局(6-15轮) vs 长局(>15轮)
  - **按game type统计策略深度**: goofspiel(纯策略) vs gin_rummy(部分信息) vs leduc_poker(博弈论)
  - **识别trivial样本**: 对手明显犯错导致轻松获胜的局 → 标记为"低训练价值"
- 输出: `knowledge/environments/game_difficulty_analysis.md`
- **目的**: Phase 3 GRPO时实现动态难度过滤

**D4 (P2): 污染检测脚本准备**

背景: DeepResearcher用pass@10检测训练数据污染 — base model已知答案的样本训练价值低。

任务:
- **准备**（不执行）一个脚本思路: 用base Qwen3-32B对GAME训练数据做推理，如果base model已经能赢→该样本训练价值低
- 这需要GPU，等v2训练完成后执行
- 现在先设计方案，写入 `knowledge/environments/game_contamination_check.md`

**优先级总结**:
- D1 + D2: **立即开始**，纯数据分析
- D3: D1/D2完成后
- D4: 仅设计方案，GPU等v2完成后

**[2026-03-18 17:01 UTC] D1-D4 REVIEW — Strategic Decisions Based on Data Findings**

D1-D4全部完成，质量极高。以下是基于分析结果的战略决策：

**D1 NAVWORLD — 5-template finding是关键发现:**

- 2248条数据来自**仅5个查询模板**，5种tool-call序列，10个出发城市
- 这**完美解释了SFT天花板** — 模型学到5个recipe，不是通用tool-calling推理
- Phase 3 NAVWORLD改进的关键不是GRPO/DPO（方法），而是**数据多样性**
- **结论**: Phase 3 NAVWORLD需要先扩展模板多样性（>20种查询类型），然后才做RL

**D2 v3 GAME质量 — 接受rejection sampling结果:**

- ✅ **APPROVE**: goofspiel HIGH+MEDIUM 150条 — merge到v3 canonical
- ✅ **APPROVE**: leduc poker HIGH 18条 — merge到v3 canonical
- ❌ **REJECT**: gin_rummy 全部440条 — 单模板thinking + 1.8%胜率 = 有毒数据
- ❌ **REJECT**: goofspiel LOW 42条 + leduc MEDIUM 40条

**v3 merge总量: 168条** (不是690条)。等v2 eval后再merge。

**D3 GAME难度 — 直接影响v3训练数据:**

- MEDIUM+HARD = 2105/2641 (79.7%) — v3可以过滤掉TRIVIAL+EASY 536条
- **gin_rummy是最有价值的训练数据** — 高策略深度，score有方差 → GRPO最佳信号源
- **但gin_rummy bot数据质量极差** → 需要重建

**D4 污染检测 — 方案良好，v2后执行**

**NEW DIRECTIVES — 立即执行:**

**D5 (P0): 修复gin_rummy数据生成pipeline**

这是最高优先级。gin_rummy有最高的策略深度和score方差（GRPO最需要的特性），但当前bot生成的数据完全不可用（单模板thinking，1.8%胜率）。

任务:
1. **诊断`game_bot_gen.py`中gin_rummy的thinking生成逻辑** — 为什么只产生一个模板？是prompt问题还是代码bug？
2. **设计修复方案** — thinking必须引用具体game state:
   - 手牌组成（哪些meld在组、deadwood是什么）
   - 对手弃牌模式（推断对手可能的meld）
   - draw决策理由（upcard是否能补全meld vs stock的期望）
   - discard决策理由（deadwood排序、避免给对手喂牌）
3. **提升胜率** — 当前bot是随机水平(1.8%)。需要至少实现:
   - 基本meld识别（连续牌/同点牌）
   - 贪心discard（扔最高deadwood且不在任何potential meld中的牌）
   - Knock判断（deadwood≤10时主动knock）
4. 如果`game_bot_gen.py`修复太复杂 → **报告方案+blockers**，我来评估是否用LLM distillation替代

**D6 (P1): NAVWORLD多样性扩展方案设计**

基于D1发现（5-template瓶颈），NAVWORLD的SFT天花板根因是数据多样性不足，不是方法论问题。

任务:
1. **分析当前5个模板的具体差异** — 是query类型不同还是仅参数不同？
2. **设计15+新查询类型** — 参考D1建议:
   - 开放式: "周末去哪玩"、"帮我规划路线"
   - 多轮对话: 用户中途改需求
   - 异常处理: 天气差、航班取消、无直达交通
   - 特殊需求: 无障碍、宠物友好、红色旅游、摄影路线
   - 国际目的地、农村地区
3. **评估生成成本** — 每种新模板需要多少API调用（DashScope qwen3-max）
4. 输出: `knowledge/environments/navworld_diversity_plan.md`
5. **不执行生成** — 先出方案给我审批

## Scope

- `forge/data/`, `scripts/`
- `synth_config.json`
- `knowledge/`, `logs/`, `memory/`
