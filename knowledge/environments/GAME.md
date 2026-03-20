# GAME Environment

## Key Facts
- Scheduling weight 3.0 (sampled 3x more often by validators — more data points, NOT 3x scoring weight)
- Scoring uses geometric mean across all environments equally — no per-env weight multiplier
- Multi-turn gameplay, assistant replies are often single digits (action IDs)
- Eval uses OpenSpiel framework, **7 games active** (not all 22)
- `strip_think_tags=True` in eval — think blocks are auto-stripped
- 2 retry mechanism: model gets a second chance on parse errors
- Scoring: win/loss/draw per game, averaged across samples
- Leaderboard top scores: ~45-65 points

## Active Games

Source: `affine-cortex/affine/database/system_config.json`
dataset_range: `[[0, 500000000], [600000000, 800000000]]`

| idx | Game | task_id range | Actions | State Format | Canonical (bot+distill) |
|-----|------|--------------|---------|-------------|------------------------|
| 0 | **goofspiel** | 0-99M | 1-13 (bids) | Simple points | 381 + ~153 GPT |
| 1 | **liars_dice** | 100M-199M | ~20 (bids+call) | Custom formatted | 245 + ~894 GPT |
| 2 | **leduc_poker** | 200M-299M | 2-3 (fold/call/raise) | Custom formatted | 223 + ~357 GPT |
| 3 | **gin_rummy** | 300M-399M | 3-54 (draw/discard) | Card state | 1320 |
| 4 | **othello** | 400M-499M | 3-30 (board positions) | Raw 8×8 board | 541 |
| 5 | backgammon | 500M-599M | ❌ excluded | — | — |
| 6 | **hex** | 600M-699M | 3-25 (coordinates) | Raw diamond grid | 452 + ~38 GPT |
| 7 | **clobber** | 700M-799M | 5-50 (captures) | Raw rectangular grid | 469 + 3 GPT |
| 8+ | hearts, euchre, etc. | 800M+ | ❌ not in eval range | — | — |

## Zero-Score Root Cause Analysis (2026-03-20)

**v2.1/v2.2 result**: othello, hex, clobber, liars_dice all 0%. Root cause is NOT that model can't play — it's **eval parsing + state representation**:

### 1. Parsing Failures (PRIMARY)
Eval parser (`llm_bot.py` lines 223-285) tries: pure number → number in text → action string match.
- **Scoring games** (leduc/goofspiel): Actions are simple integers (0,1,2). Unambiguous parsing.
- **Zero-score games** (hex/clobber): Actions use coordinate notation (e.g., `12 -> c3`). Model reasoning contains numbers ("3-step lookahead") that confuse the number extractor.
- Parse failure × 2 retries → `ParsingError` → score=0.0 counted as valid sample.

### 2. State Representation Gap
- **Scoring games**: Have custom `format_state()` that converts raw OpenSpiel → English. E.g., LeducPokerAgent: `"36 1-3"` → `"Your card: K♠, Pot: 6 chips"`.
- **Zero-score games**: Use raw `observation_string()` (ASCII board grids). Model can't parse spatial board → can't reason → outputs wrong action.

### 3. Action Space Size
| Game | Typical legal actions | Parsing difficulty |
|------|----------------------|-------------------|
| leduc_poker | 2-3 | Trivial |
| goofspiel | ~8 | Easy |
| liars_dice | 2-15 | Medium |
| gin_rummy | 3-20 | Medium |
| hex | 3-25 | Hard (coordinates) |
| othello | 3-30 | Hard (board positions overlap reasoning) |
| clobber | 5-50 | Hard (coordinate notation) |

### Solution Priority
1. **P0 (SFT-fixable)**: GPT-5.4 distillation teaches correct output format per game — model learns to output clean `ACTION_ID` after think block
2. **P1 (Data)**: Ensure training system prompts match eval system prompts exactly
3. **P2 (Method)**: GRPO with game outcome reward — bypasses parsing issue by reinforcing winning patterns
4. **P3 (Eval)**: If format issues persist, consider whether eval agent `format_state()` can be improved (read-only for us)

## Format Requirements
- System prompt tells model to respond with action ID
- Assistant reply: `<think>English strategy reasoning</think>\nACTION_ID`
- Eval parser extracts the number; anything else = parse error
- **Critical**: Think block must NOT contain bare numbers that could be mistaken for action IDs

## Data Status (2026-03-20)

### Canonical: 3631 entries (v5 — qwen3-max distillation removed)
| Game | Count | Source | Notes |
|------|-------|--------|-------|
| gin_rummy | 1320 | bot_strategy | think diversity improved to 34% |
| othello | 541 | bot_strategy | think diversity low (2.3%), needs improvement |
| clobber | 469 | bot_strategy | think diversity low (1.0%) |
| hex | 452 | bot_strategy | think diversity low (2.1%) |
| goofspiel | 381 | bot_strategy | qwen3-max removed, GPT-5.4 distill in progress |
| liars_dice | 245 | bot_strategy | 74% trivial (≤2 turns), GPT-5.4 distill in progress |
| leduc_poker | 223 | bot_strategy | qwen3-max removed, GPT-5.4 distill in progress |

### v5 Changes (2026-03-20)
- **Removed 1026 qwen3-max distillation entries** (goofspiel 741 + leduc_poker 285)
  - Reason: qwen3-max produced Chinese think blocks (66% of goofspiel, 57% of leduc)
  - leduc_poker distill had inferior action quality (avg score 0.607 vs bot 0.827)
  - qwen3-max liars_dice had empty dice bug (`My dice []`)
- **GPT-5.4 re-distillation in progress** — replacing with higher quality data
  - GPT-5.4 produces English strategic reasoning with game-theory depth
  - Action quality equal or better than bot (leduc 0.914 vs qwen3-max 0.607)
  - Think diversity far superior (real analysis vs templates)

### GPT-5.4 Distillation (in progress)
| Game | Seeds | Wins so far | Target |
|------|-------|------------|--------|
| liars_dice | 500 | ~92 | ~250 |
| leduc_poker | 600 | ~47 | ~240 |
| goofspiel | 800 | ~16 | ~400 |
| hex | 300 | ~4 | ~60-150 |
| clobber | 300 | starting | ~60-150 |

- Script: `scripts/game_distill.py` — GPT-5.4 plays OpenSpiel games via API
- Win rate varies by game: liars_dice ~51%, leduc ~39%, goofspiel ~46%, hex ~20%
- All distilled data: 100% English, diverse thinks, real game-theory reasoning
- Will be merged with existing bot data for v2.4 training

## Data Generation Pipeline

| Tool | Purpose | Usage |
|------|---------|-------|
| `scripts/game_bots.py` | Bot strategies for all 7 games | Imported by gen scripts |
| `scripts/game_bot_gen.py` | Bot vs random, records wins | `--game X -n 500` |
| `scripts/game_distill.py` | GPT-5.4 plays games | `--games X,Y -n 50` |
| `scripts/game_data_clean.py` | Audit/clean canonical data | `--audit` or `--all` |
| `scripts/game_think_regen.py` | Batch think regeneration via LLM | `--input X --all` |

- pyspiel installed via `.pylibs/`
- Can regenerate unlimited data for any game

## Evaluation Setup
- `--concurrency 4 --timeout 7200` (old 600s timeout missed long games)
- Temperature: 0.7, Memory: 2GB
- Docker image: openspiel:eval

## Historical Results
- v2.1: GAME=25.74 (3/7 games scoring, 4 at 0%)
- v2.2: GAME=26.04 (same 3 games, 4 still 0%)
- v2.3: GAME eval running (~44/100), same pattern expected
- Zero-tier root cause: **eval parsing failure**, not SFT inability (see analysis above)

## Score Ceiling Analysis
| Scenario | Learnable avg | "Unlearnable" avg | GAME Score |
|----------|---------------|-------------------|------------|
| v2.1 actual | ~60% | 0% | 25.7 |
| Max learnable only | ~87% | 0% | 37.1 |
| +10% on unlearnable | ~87% | 10% | 42.9 |
| Match #6 (43.94) | ~87% | 20% | 48.6 |
| #1 target (46.94) | ~92% | 30% | 56.4 |

## Improvement Directions
- **P0: GPT-5.4 distillation** — fix zero-tier parsing by teaching clean output format (in progress)
- **P1: System prompt alignment** — ensure training prompts match eval exactly
- **P2: GRPO/RL** — verifiable reward (win/lose) for Phase 3
- **P3: DPO** — 589 GAME pairs available as fallback
