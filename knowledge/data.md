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

## Current Canonical Data (2026-03-20 16:00 UTC)
| Env | Count | Source | Status |
|-----|-------|--------|--------|
| GAME | 3918 | Bot + GPT-5.4 distill (7游戏均衡) | liars_dice 250, leduc 300, goofspiel 787 |
| NAVWORLD | **1157** | GPT-5.4 + Claude (零qwen-max) | 100%工具多样, avg 11.6 tools/entry |
| LIVEWEB | 400 | Historical + GPT-5.4 | LIVEWEB 15.77 突破 |
| SWE-Infinite | 22 轨迹 | GPT-5.4 fix trajectories (Go 21, Ruby 1) | 待纳入训练 |

## Key Data Lessons (confirmed by v2.4b)
- **qwen-max 数据有毒**: 2205条5模板数据导致 NAVWORLD 从 8.47→1.52, 移除后恢复到 4.58
- **seq=16384 无害**: v2.4b 用 16384 NAVWORLD 仍恢复, 证明不是 seq 的问题
- **GPT-5.4 蒸馏有效**: GAME leduc 50.8 新高, LIVEWEB 15.77 突破
- **零分游戏是 eval 问题**: liars_dice 250条GPT-5.4仍=0, 非数据可修复

## Data Mix Strategy
- Quality > quantity: qwen-max 清理后数据量减半但效果大幅提升
- Cross-family distillation only (GPT-5.4/Claude → Qwen3-32B)
- qwen-max 已全面淘汰
- 工具多样性是 NAVWORLD 的关键指标 (100% ≥3 tools)
