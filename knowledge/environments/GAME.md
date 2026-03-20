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

| idx | Game | task_id range | Status | Bot Win Rate | Canonical |
|-----|------|--------------|--------|-------------|-----------|
| 0 | **goofspiel** | 0-99M | Solved (100% win) | 98% | 1122 |
| 1 | **liars_dice** | 100M-199M | Data quality fixed, awaiting eval | 97% | 245 |
| 2 | **leduc_poker** | 200M-299M | Strong | 59% | 508 |
| 3 | **gin_rummy** | 300M-399M | Bot-improved | 97% | 1320 |
| 4 | **othello** | 400M-499M | Data rebuilt (was 12→541), awaiting eval | 75% | 541 |
| 5 | backgammon | 500M-599M | ❌ excluded from eval | — | — |
| 6 | **hex** | 600M-699M | Data rebuilt (was 190→452), awaiting eval | 55% | 452 |
| 7 | **clobber** | 700M-799M | Data rebuilt (was 123→469), awaiting eval | 59% | 469 |
| 8+ | hearts, euchre, etc. | 800M+ | ❌ not in eval range | — | — |

**Only idx 0-4 and 6-7 are evaluated.** All 7 now have substantial high-quality data.

## Format Requirements
- System prompt tells model to respond with action ID
- Assistant reply: `<think>English strategy reasoning</think>\nACTION_ID`
- Eval parser extracts the number; anything else = parse error

## Data Status (2026-03-20)

### Canonical: 4657 entries (v4 final — all batches merged)
| Game | Count | % | Source Mix |
|------|-------|---|-----------|
| gin_rummy | 1320 | 28.3% | bot_strategy + historical |
| goofspiel | 1122 | 24.1% | bot_strategy + distillation |
| othello | 541 | 11.6% | bot_strategy (v4 new) |
| leduc_poker | 508 | 10.9% | bot_strategy + distillation |
| clobber | 469 | 10.1% | bot_strategy (v4 new) |
| hex | 452 | 9.7% | bot_strategy (v4 new) |
| liars_dice | 245 | 5.3% | bot_strategy (v4 fixed) |

- **All 7 games covered** — no more zero-tier
- 100% think blocks, 0% Chinese, all English strategic reasoning
- Win-only filtering (bot win rate 55-98%)

### v4 Quality Improvements (2026-03-20)
- **1026 Chinese think entries** → translated to English via GPT-5.4
- **545 no-think entries** → removed
- **14351 template thinks** → regenerated with diverse strategic reasoning
- **liars_dice bot dice parse bug** → fixed (was always showing `[]`)
- **gin_rummy think diversity** → 1.4% → 87% unique
- **"Unlearnable" games proven learnable** → bots win at 55-79%, old 0% was data quality issue

### LLM Distillation (in progress)
- Script: `scripts/game_distill.py` — GPT-5.4 plays OpenSpiel games
- 54 entries produced so far (liars_dice 30, leduc_poker 18, hex 4, othello 2)
- Higher quality thinks than bot data (real LLM strategic reasoning)
- Will be merged as supplementary data for v2.4+

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
- v2.2: trained, awaiting eval
- v2.3: data ready (4657 GAME entries, all 7 games), awaiting training

## Score Ceiling Analysis
| Scenario | Learnable avg | "Unlearnable" avg | GAME Score |
|----------|---------------|-------------------|------------|
| v2.1 actual | ~60% | 0% | 25.7 |
| Max learnable only | ~87% | 0% | 37.1 |
| +10% on unlearnable | ~87% | 10% | 42.9 |
| Match #6 (43.94) | ~87% | 20% | 48.6 |
| #1 target (46.94) | ~92% | 30% | 56.4 |

## Improvement Directions
- **P0: Evaluate v2.3** — first test with all 7 games having data
- **P1: DPO on game outcomes** — 589 GAME pairs available
- **P2: GRPO/RL** — verifiable reward (win/lose) makes GAME ideal for RL
- **P3: More LLM distillation** — GPT-5.4 produces highest quality thinks
