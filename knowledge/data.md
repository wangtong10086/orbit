# Data Knowledge

## Key Facts
- Primary sources: synthetic generation (NAVWORLD, GAME bots, LIVEWEB pipeline), historical high-score samples
- Storage: HuggingFace private repos (JSONL format)
- Canonical format: `messages` list (chat format) or `text` field (apply_chat_template output)
- CLI: `forge data audit`, `forge data ingest`, `forge data canonical-upload`, `forge data analyze`

## apply_chat_template (Critical)
- **Must use** `tokenizer.apply_chat_template(messages, tools=tools)` for tool-calling data
- Generates native Qwen3 format: `<tool_call>`, `<tool_response>`, `<tools>` tags
- Without this, custom serialization produces wrong format that eval cannot parse
- v7 used custom `<tool_calls>JSON</tool_calls>` → all NAVWORLD zeros
- v8 switched to apply_chat_template → NAVWORLD broke through to 0.087
- LIVEWEB: `_normalize_tool_calls_qwen3()` required in prepare-data (discovered 2026-03-20)

## Data Format by Environment
| Env | Format | Key Fields |
|-----|--------|-----------|
| GAME | messages (system + alternating user/assistant) | assistant = pure number or think+number |
| NAVWORLD | messages with tool_calls + tool role | Must use apply_chat_template with tools= |
| SWE-SYNTH | messages (multi-turn, THOUGHT + bash) | No think tags, ends with assistant |
| LIVEWEB | messages (free think + JSON action) | Needs `<tool_call>` Qwen3 format + `<tools>` definitions |

## Data Generation Methods

### GAME — Bot strategies (programmatic)
- `scripts/game_bots.py`: deterministic game-playing bots for 7 games
- Not LLM distillation — pure game logic
- Proved effective: gin_rummy broke through 0% after inclusion

### NAVWORLD — Claude Sonnet distillation + QQR filtering
- `forge/data/navworld_gen.py`: programmatic tool call sequence → real Amap API → LLM generates plan
- Claude Sonnet entries score 40-46/100 on QQR (vs qwen-max 0/100)
- QQR filter: remove entries scoring <25 on code-based quality scorer

### LIVEWEB — Claude/GPT distillation pipeline
- `scripts/liveweb_real_gen.py`: Claude/GPT agent browses real sites + Claude validator scores
- Supports `--plugin` for targeting specific plugins (8 active in eval)
- Includes trajectory pruning + tree compression (-66% token reduction)
- API: codex proxy with gpt-5.4 (or any OpenAI-compatible endpoint)

### SWE-SYNTH — Historical high-score samples
- 983 clean entries from historical eval data
- Think tag contamination cleaned (368 entries removed)

## Environment-Specific Cleaners
- GAME: verify complete gameplay, deduplicate, unify system prompt (CoT version)
- NAVWORLD: verify poi_search + weather + direction all present, remove text-format entries
- SWE-SYNTH: remove trailing user messages, verify THOUGHT+bash format, no think tags
- LIVEWEB: normalize tool_calls to Qwen3 format, add tool definitions to system prompt

## Data Mix Strategy
- Geometric mean scoring → cannot ignore any environment
- Quality > quantity: format errors worse than missing data
- seq=16384 confirmed safe: doesn't dilute short-entry envs (GAME)

## Current Canonical Data (2026-03-20)
| Env | Count | Source |
|-----|-------|--------|
| GAME | 3316 | Bot strategies + historical |
| NAVWORLD | 2624 | Claude Sonnet + qwen-max (QQR filtered) |
| SWE-SYNTH | 983 | Historical (cleaned) |
| LIVEWEB | 356+ | Historical + pipeline (expanding) |

## Improvement Directions
- LIVEWEB plugin diversity (8 eval plugins, currently cover 2)
- More NAVWORLD Claude Sonnet data (341 → 500+ target)
- GAME othello data volume (only 12 entries)
- DPO alignment after SFT stabilizes
