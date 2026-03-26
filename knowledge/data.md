# Data Knowledge

## Key Facts
- Primary sources: bot strategies (GAME), Claude/GPT-5.4 distillation (NAVWORLD, LIVEWEB), GitHub PR mining (SWE-Infinite)
- Storage: HuggingFace private repo `monokoco/affine-sft-data` (JSONL format)
- Canonical format: `messages` list (chat format), converted via `tokenizer.apply_chat_template`
- CLI: `forge data audit`, `forge data ingest`, `forge data canonical-upload`, `forge data analyze`

## apply_chat_template (Critical)
- **Must use** `tokenizer.apply_chat_template(messages, tools=tools)` for tool-calling data
- Generates native Qwen3 format: `<tool_call>`, `<tool_response>`, `<tools>` tags
- LIVEWEB: `_normalize_tool_calls_qwen3()` in prepare-data converts OpenAI format → Qwen3 XML
- Without correct format, NAVWORLD and LIVEWEB score 0

## Data Format by Environment
| Env | Format | Key Fields |
|-----|--------|-----------|
| GAME | messages (system + alternating user/assistant) | assistant = think block + action ID |
| NAVWORLD | messages with tool_calls + tool role | Must use apply_chat_template with tools= |
| SWE-Infinite | messages (multi-turn, THOUGHT + bash) | No think tags, ends with assistant |
| LIVEWEB | messages with tool_calls | Needs `<tool_call>` Qwen3 format + `<tools>` definitions |

## Data Generation Methods

### GAME — Bot strategies + GPT-5.4 distillation
- `scripts/game_bots.py`: deterministic game-playing bots for 7 games
- `scripts/game_distill.py`: GPT-5.4 distillation for think diversity
- v4: all 7 games covered, 100% English thinks, diverse reasoning

### NAVWORLD — V5 GPT-5.4 distillation (eval-aligned)
- `forge/data/navworld_gen.py`: programmatic tool calls → real Amap API → LLM plan gen → QQR filter
- **V5 complete**: 1426 entries, all eval-aligned (Chinese prompts/schema/transport)
- All qwen-max and pre-V5 data removed (format bugs)
- Quality gate: QQR code score ≥25, fabrication filtering

### LIVEWEB — GPT-5.4 distillation pipeline
- `scripts/liveweb_real_gen.py`: agent browses real sites + validator scores
- GPT-5.4 via codex proxy, all score=1.0 entries
- Supports per-plugin targeting (8 active in eval)
- No compression needed — 100% fit seq=16K

### SWE-Infinite — GitHub PR trajectory collection
- `scripts/swe_distill.py`: GPT-5.4 fixes real GitHub PR bugs → training trajectories
- Only score=1.0 trajectories kept
- Format: THOUGHT + bash (NOT tool_calls)
- See `knowledge/environments/SWE-INFINITE.md`

## Current Canonical Data (2026-03-22)
| Env | Count | Source | Status |
|-----|-------|--------|--------|
| GAME | **4462 (v11 MCTS)** | MCTS bot strategies (all 7 games, 60-80% win) | goofspiel 953, liars_dice 1000, clobber 998, leduc 525, gin_rummy 572, othello 325, hex 89 |
| NAVWORLD | ~1619 (V5) | GPT-5.4 distill, eval-aligned | V5 complete, all format-fixed, growing |
| LIVEWEB | ~754 | Historical + GPT-5.4 + multi-step | Format fixes applied, multi-step 48% |
| SWE-Infinite | ~126 | GPT-5.4 fix trajectories | Go-dominant. Excluded from training (toxic). |

## Key Data Lessons
- **qwen-max data is poison**: 2205 entries caused NAVWORLD 8.47→1.52. All removed.
- **NAVWORLD format alignment is critical**: V5 fixed 3 format mismatches (transport/prompts/schema).
- **GAME spatial games**: 0% with MCTS stats data. v9 rule-based think data targeting 15-22%.
- **SWE-I is toxic to SFT**: 215 entries hurt GAME/LW in v2.10. Excluded since v2.11.
- **Data proportions matter**: v2.7 optimal ratio was GAME 59%, NW 26%, LW 15%. Deviation degrades scores.
- **epochs=2 overfits**: v2.8 showed catastrophic regression on all envs. Use epochs=1 only.
- **GPT-5.4 distillation effective**: best source for NAVWORLD, LIVEWEB, SWE-I data.

## Data Mix Strategy
- Quality > quantity: qwen-max 清理后数据量减半但效果大幅提升
- Cross-family distillation only (GPT-5.4/Claude → Qwen3-32B)
- qwen-max 已全面淘汰
- 工具多样性是 NAVWORLD 的关键指标 (100% ≥3 tools)
