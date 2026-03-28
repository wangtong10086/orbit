# Data Knowledge

## Current Canonical Data (2026-03-28)

| Env | Count | File | Format | Notes |
|-----|-------|------|--------|-------|
| GAME | 38663 | game.jsonl | messages, no think, no tools | All 7 games, MCTS bots, bare action IDs |
| MemoryGym | 20000 | memorygym.jsonl | messages, no tools | ChromaDB interaction, very long (P50=49k tokens) |
| LW | 17108 | liveweb.jsonl | messages + tool_calls | goto+stop only, no think, 4 domains |
| NW | 10006 | navworld.jsonl | messages + tool_calls | 7 types balanced, GPT-5.4, Chinese prompts |
| SWE-I | 1605 | swe_infinite.jsonl | messages, THOUGHT+bash | Go ~95%, no think tags |
| **Total** | **87382** | | | |

## Storage
- Canonical: `data/canonical/*.jsonl`
- HF: `monokoco/affine-sft-data` (private)
- Training: combined.jsonl (shuffled mix of all envs)

## Key Facts
- **Mixed schema**: 24.4% of entries have tool_calls/tool_call_id fields. PyArrow can't load mixed schema — use json.loads() or ms-swift (handles natively)
- **Token lengths**: GAME ~1.4k, NW ~14k, LW ~12k, SWE-I ~13k, MemoryGym ~49k (97% truncated at 32k)
- **No think chains**: all envs use pure action/tool_call format, no `<think>` tags
- **Shuffling required**: if GAME (no tool_calls) first in batch, schema inference breaks

## Data Lessons
- **qwen-max data is poison**: removed, GPT-5.4/Claude only
- **GAME data quality critical**: buggy data cross-contaminates all envs (v2.24)
- **epochs=1 only**: v2.8 proved 2 epochs overfits catastrophically
- **NW format alignment critical**: must match eval transport/prompts/schema
- **Combined JSONL must be shuffled**: prevents schema inference bugs
