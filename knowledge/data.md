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

### NAVWORLD — GPT-5.4 + Claude Sonnet distillation
- `forge/data/navworld_gen.py`: programmatic tool calls → real Amap API → LLM plan gen → QQR filter
- GPT-5.4 entries being generated (V2 all-type, replacing qwen-max)
- Claude Sonnet: 419 entries, avg 39.7/50 code score
- Quality gate: QQR code score ≥25

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

## Current Canonical Data (2026-03-20)
| Env | Count | Source | Status |
|-----|-------|--------|--------|
| GAME | ~4657 | Bot strategies + GPT-5.4 distill | v4 complete, all 7 games |
| NAVWORLD | 2725+ | Claude Sonnet (419) + GPT-5.4 (101+) + qwen-max (2205) | GPT-5.4 replacing qwen-max |
| LIVEWEB | 365 | Historical (341 cleaned) + GPT-5.4 (24) | Growing |
| SWE-Infinite | 0 | Pipeline building | data-swe role owns |

## v2.4 Data Plan (next training)
- NAVWORLD: remove all 2205 qwen-max, keep 419 Claude + ~1200 GPT-5.4
- SWE-SYNTH: removed (environment deprecated)
- GAME/LIVEWEB: use latest canonical

## Data Mix Strategy
- Geometric mean scoring → cannot ignore any environment
- Quality > quantity: format errors worse than missing data
- Cross-family distillation preferred (GPT-5.4/Claude → Qwen3-32B)
- Same-family distillation (qwen-max → Qwen3-32B) being phased out
