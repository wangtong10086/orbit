# Data Augmentation System Plan

## Overview

| Env | Current Data | Method | Feasibility | Cost/Entry | Priority |
|-----|-------------|--------|-------------|------------|----------|
| **GAME** | 680 | Distillation (local engine + LLM API) | ⚠️ Need to install pyspiel | ~$0.007 | |
| **NAVWORLD** | 510 | Synthesis (AMap API + LLM) | ✅ Verified | ~$0.005 | ✅ Target met |
| **LIVEWEB** | 165+19 | Distillation (Playwright + LLM) | ✅ Verified | ~$0.01 | 🔴 High (weakest env) |
| **SWE-SYNTH** | 469 | Distillation (Docker container + LLM) | ❌ Need Docker permission | ~$1-5 | 🟡 Medium (needs authorization) |
| **MEMORYGYM** | 500 | Synthesis (pure simulation, zero cost) | ✅ Immediately available | $0 | 🟢 Awaiting launch |

---

## 1. GAME — Distillation (Local OpenSpiel Engine + Strong Model API)

### Why Distillation?
- The game engine (OpenSpiel) is deterministic; the LLM only provides decisions
- Win/loss automatically verified per game (score precisely calculated)
- Needs a real opponent (MCTS bot) to produce meaningful matches

### Technical Path
```bash
# 1. Install pyspiel
pip install open-spiel

# 2. Run locally: game engine + MCTS opponent (local) + LLM decisions (remote API)
python3 scripts/game_gen.py \
  --games "goofspiel,hex,liars_dice,leduc_poker,othello" \
  --seeds-per-game 50 \
  --model deepseek-ai/DeepSeek-V3-0324 \
  --min-score 0.7 \
  -o data/game_gen.jsonl
```

### Quality Control
- score ≥ 0.7 (only wins or high-score draws)
- Game type balance (currently Goofspiel at 38%, needs reduction)
- Prioritize fast games (Liars Dice ~6 rounds, Goofspiel ~10 rounds); slow games (Chess, Go) as needed
- Format verification: assistant reply must be a pure numeric action ID

### Pilot Results (DeepSeek-V3 vs MCTS)

| Game | Success/Attempts | Success Rate | Notes |
|------|-----------------|-------------|-------|
| goofspiel | 3/3 | 100% | ⭐ Best |
| blackjack | 1/2 | 50% | Single player game |
| leduc_poker | 0/2 | 0% | Score near threshold |
| liars_dice | 0/5 | 0% | MCTS too strong |
| euchre | 0/3 | 0% | 4-player slow game |

### Estimates (Revised)
- Success rate varies widely by game: goofspiel ~100%, most games <30%
- Need more seeds and more game types to accumulate data
- Consider lowering min_score to 0.5 (existing DDB data is also 0.5+)

---

## 2. NAVWORLD — Synthesis (AMap API + LLM Generation) ✅ Complete

### Why Synthesis?
- Does not require full environment to run (AMap provides real geographic data)
- LLM generates travel plans (simulating agent behavior)
- Mature pipeline exists: `navworld_gen.py`

### Current Status
- 510 entries in tool_call format, all score=1.0
- Exceeded 500 entry target
- Pipeline command: `python3 -m forge data navworld-gen -n <N> -o <output> --start-id <ID>`

### Continuous Augmentation
- Can append at any time, ~$0.005 per entry
- Focus: increase question type diversity (intercity, multiday, food_tour, business, hybrid)

---

## 3. LIVEWEB — Distillation (Playwright Browser + Strong Model API)

### Why Distillation?
- Must actually browse real web pages (Playwright automation)
- Ground truth obtained from APIs in real-time (dynamic data)
- Single-task success rate much higher than multi-task

### Pilot Results

| Plugin | Success/Attempts | Success Rate | Issues |
|--------|-----------------|-------------|--------|
| CoinGecko | 17/18 | 94% | ✅ Extremely stable |
| HackerNews | 1/3 | 33% | ⚠️ Needs investigation |
| Stooq | 1/3 | 33% | ⚠️ GT collection issue |
| Taostats | 0/9 | 0% | ❌ All failed, needs fix |

### Technical Path
```bash
# Existing script
python3 scripts/liveweb_gen.py \
  --templates coingecko hackernews \
  --seeds-per-template 20 \
  --min-score 0.8 \
  -o data/liveweb_gen.jsonl
```

### Current Blockers and Fix Plan
1. **Taostats all failed** — need to analyze GT collection logic, possibly API format change
2. **Stooq low success rate** — also needs investigation of GT/validation issues
3. **Cache permissions** — resolved via `LIVEWEB_CACHE_DIR=/tmp/liveweb-cache`

### Phased Execution
- **Phase 1** (immediately): CoinGecko 8 templates × 20 seeds = 160 entries (estimated ~140 successful)
- **Phase 2** (after fixes): Stooq + Taostats after fix, 17 templates × 15 seeds = ~120 entries
- **Phase 3** (expansion): HackerNews + Hybrid = ~50 entries
- **Total target**: 300+ high-quality single-task entries

---

## 4. SWE-SYNTH — Distillation (Docker Container + Fixer Agent)

### Why Distillation?
- Must fix bugs in real code repositories
- Verification requires running test suites (Docker hard requirement)
- Scoring is binary (1.0 all tests pass or 0.0)

### Current Limitations
- **Insufficient Docker permissions** (current user `dev` not in docker group)
- Requires user authorization: `sudo usermod -aG docker dev`

### If Docker Permission Granted
```bash
# Use SWE-bench Pro tasks + miniswe fixer agent
python3 scripts/swe_gen.py \
  --task-ids 0-200 \
  --model deepseek-ai/DeepSeek-V3-0324 \
  --min-score 1.0 \
  --concurrency 3 \
  -o data/swe-synth_gen.jsonl
```

### Estimates
- ~$1-5 per entry (LLM multi-turn calls + Docker container)
- 5-30 minutes per entry
- Estimated success rate ~30-50% (complex bug fixes)
- 131 entry gap → need ~300-400 attempts

---

## 5. MEMORYGYM — Synthesis (Pure Simulation, Zero Cost) 🟢

### Why Synthesis?
- Fully deterministic simulation (no LLM calls)
- Zero cost, generates in seconds
- Two strategies: perfect (100% storage) and strategic (70% selective storage)

### Generation Command
```bash
cd ../MemoryGym
python3 -m memorygym.training data -o <output> --seeds 100 --strategy perfect
python3 -m memorygym.training data -o <output> --seeds 100 --strategy strategic
```

### Current Status
- 500 entries generated (250 perfect + 250 strategic)
- MEMORYGYM has not appeared on leaderboard → not training yet
- **Trigger condition**: `python3 -m forge data envs` shows MEMORYGYM → immediately generate in bulk

---

## Execution Priority

```
Execute immediately:
  1. LIVEWEB Phase 1 — CoinGecko full template distillation (~140 entries)
  2. GAME — Install pyspiel + write generation script + pilot

Needs authorization:
  3. SWE-SYNTH — Needs Docker permission

Continuous monitoring:
  4. NAVWORLD — Target met, append as needed
  5. MEMORYGYM — Wait for leaderboard appearance
```

## Automation Integration

All generators are managed through `synth_config.json`. The **routine tasks** in the Data Synthesis Agent loop protocol auto-trigger:
- Quality check → find low quality → clean
- Target not met → auto synthesis/distillation to supplement
- DynamoDB refresh → new data imported
