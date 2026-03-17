# Data Knowledge

## Key Facts
- Primary source: DynamoDB `affine_sample_results` (high-score samples from all miners)
- Secondary: synthetic generation (NAVWORLD, GAME bot strategies)
- Storage: HuggingFace private repos (JSONL format)
- Canonical format: `messages` list (chat format) or `text` field (apply_chat_template output)
- CLI: `forge data refresh`, `forge data extract`, `forge data upload`, `forge data merge`

## DynamoDB Extraction
- `forge/data/dynamo.py` handles DDB queries
- `forge/data/sft.py` handles SFT data extraction and cleaning
- Filter by: environment, min score, max chars
- `forge data extract-all` for batch extraction across all environments
- DPO extraction: `forge data extract-dpo` groups by task_id, high=chosen, low=rejected

### DDB Data Volumes (as of 2026-03-16)
| Env | Total | Avg Score | Usable (high quality) |
|-----|-------|-----------|----------------------|
| LGC-v2 | 21,757 | 0.669 | 3,353 (>=0.7, <=16K) |
| PRINT | 17,689 | 0.734 | 2,899 (>=0.7, <=16K) |
| LIVEWEB | 15,844 | 0.172 | ~3 (>=0.7, <=16K) |
| GAME | 12,984+ | 0.360 | ~930 (>=0.5) |
| SWE-SYNTH | 11,594+ | 0.335 | ~454 (>=0.5, <=32K) |
| NAVWORLD | 9,867+ | 0.060 | ~248 (>=0.3) |

## apply_chat_template (Critical)
- **Must use** `tokenizer.apply_chat_template(messages, tools=tools)` for tool-calling data
- Generates native Qwen3 format: `<tool_call>`, `<tool_response>`, `<tools>` tags
- Without this, custom serialization produces wrong format that eval cannot parse
- v7 used custom `<tool_calls>JSON</tool_calls>` → all NAVWORLD zeros
- v8 switched to apply_chat_template → NAVWORLD broke through to 0.087

## Data Format by Environment
| Env | Format | Key Fields |
|-----|--------|-----------|
| GAME | messages (system + alternating user/assistant) | assistant = pure number or think+number |
| NAVWORLD | messages with tool_calls + tool role | Must use apply_chat_template with tools= |
| SWE-SYNTH | messages (multi-turn, THOUGHT + bash) | No think tags, ends with assistant |
| LIVEWEB | messages (free think + JSON action) | Supports think tags |
| LGC-v2 | messages (think block + answer) | ~20% need Python code blocks |
| PRINT | messages (think block + answer) | Verify think block closure |

## Synthetic Data Generation
- NAVWORLD: `forge/data/navworld_gen.py`, DeepSeek-V3-0324 via Chutes API
  - Programmatic tool call sequence → real Amap API → LLM generates plan
  - 161 entries (batch 1) → v11: 2154 entries (100% direction coverage)
- GAME bot: programmatic strategy bots for 7 games (2193 entries)
  - Not LLM distillation — deterministic game-playing logic
- LIVEWEB: `scripts/liveweb_gen.py` (attempted, mostly too long)

## Environment-Specific Cleaners
- GAME: verify complete gameplay, deduplicate, unify system prompt (CoT version)
- NAVWORLD: verify poi_search + weather + direction all present, remove text-format entries
- SWE-SYNTH: remove trailing user messages, verify THOUGHT+bash format
- LIVEWEB: filter by length (<= 16K chars)
- LGC-v2: don't require Python code blocks for all tasks
- PRINT: verify think block closure + answer present

## Data Mix Strategy
- Geometric mean scoring → cannot ignore any environment
- Weak environments get upsampled (2-5x)
- Strong environments get capped or downsampled
- Quality > quantity: format errors worse than missing data

## Current Best / Status
- v10 mix: 13,733 entries across 7 environments
- v11 mix: 15,273 entries (NAVWORLD +240%)
- DPO dataset: 2,688 pairs (not yet used in training)

## Improvement Directions
- Continuous DDB refresh for more high-score samples
- More NAVWORLD synthetic data with diverse scenarios
- LIVEWEB shorter-form data generation
- SWE-SYNTH longer context training support
- DPO alignment after SFT stabilizes
