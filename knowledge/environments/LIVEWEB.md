# LIVEWEB Environment

## Key Facts
- Web interaction/browsing evaluation via liveweb-arena Docker container
- Format: OpenAI function calling (tool_calls with goto/click/type/stop etc.)
- Eval uses LLM validator to compare agent answers vs ground truth
- Cannot evaluate locally — only verifiable through leaderboard deployment
- Leaderboard scores: ~14-19 points (everyone in 13-19, relatively flat)

## Eval Architecture
- **Agent**: receives accessibility tree + task prompt, outputs tool_calls
- **Actions**: goto, click, click_role, type, type_role, press, scroll, view_more, wait, stop
- **Scoring**: agent answer vs ground truth via LLM validator (0.0-1.0)
- **Plugins**: coingecko, stooq, taostats, hackernews, openlibrary, arxiv, openmeteo, hybrid
- **Weather**: DISABLED (`DISABLED_PLUGINS: set = {"weather"}`)

## Training Format

### Canonical → Training Pipeline
1. Canonical `data/canonical/liveweb.jsonl` stores OpenAI tool_calls format (raw)
2. `forge rental prepare-data` calls `_normalize_tool_calls_qwen3()` to convert:
   - System prompt → appends `# Tools` + `<tools>` XML definitions (10 browser actions)
   - Assistant tool_calls → `<tool_call>{"name": ..., "arguments": ...}</tool_call>`
   - Tool responses → `role=user` with `<tool_response>` wrapper
3. Output matches `tokenizer.apply_chat_template(messages, tools=...)` exactly

### v2.2 Format Bug (fixed)
v2.2 trained with raw JSON arrays instead of `<tool_call>` XML tags. LIVEWEB score ≈ 0.
Fixed in `_normalize_tool_calls_qwen3()` — v2.3+ uses correct format.

## Data Generation Pipeline

### Script: `scripts/liveweb_real_gen.py`

```bash
# Generate per-plugin (recommended)
python3 liveweb_real_gen.py -n 15 --plugin taostats -o output.jsonl --compression 3

# All plugins batch
for p in taostats hackernews openlibrary arxiv openmeteo stooq coingecko; do
    python3 liveweb_real_gen.py -n 15 --plugin $p -o output.jsonl --compression 3
done
```

**Architecture**:
- Agent LLM: gpt-5.4 via codex proxy (OPENAI_API_KEY + OPENAI_BASE_URL)
- Validator: same endpoint + model (VALIDATION_MODELS env var override)
- Compression: liveweb-arena native `compress_conversation(level=3, max_tree_chars=4000)`
- Export: saves trajectories with stop action, includes score + compression metadata

**Key env vars for Docker container**:
- `API_KEY` / `API_BASE_URL` — agent LLM
- `VALIDATION_MODELS` — override validator model names (must match endpoint's available models)
- `TAOSTATS_API_KEY`, `COINGECKO_API_KEY` — plugin data access

### Success Rates (2026-03-20)

| Plugin | Success Rate | Notes |
|--------|-------------|-------|
| taostats | **100%** (15/15) | click_role navigation, best quality |
| hackernews | **67%** (10/15) | page reading + summarization |
| coingecko | **80%** (12/15) | simple goto + price lookup |
| stooq | **40%** (6/15) | search + navigation |
| openlibrary | in progress | — |
| arxiv | in progress | — |
| openmeteo | in progress | — |

### Action Diversity (from 38 entries)
goto 46, click_role 39, stop 38, type_role 3, type 3, click 1

## Current Data Status

| Source | Count | Score=1.0 | Notes |
|--------|-------|-----------|-------|
| Historical DDB | 356 | 356 (100%) | CoinGecko/Stooq only, low diversity |
| Claude distill v3 | 14 | 12 | CoinGecko/Stooq, score>0 filtered |
| gpt-5.4 distill v4 | ~38+ | ~13 | Multi-plugin (taostats/hackernews/...), batch running |
| **Total canonical** | **370** | — | HF synced. v4 batch pending merge |

## Dead Ends

### DashScope qwen3-max — BLOCKED
API works for function calling but `data_inspection_failed` on ALL web accessibility tree content.
阿里云内容安全过滤器阻塞所有网页内容。无法用于 LIVEWEB 生成。

### claudecode proxy — INTERMITTENT
Endpoint `api.aicodemirror.com/api/claudecode/v1` sometimes 401/503.
When working, Claude Sonnet is the best agent (highest quality trajectories).
Fallback: codex proxy with gpt-5.4 (currently primary).

## Scaling Plan

1. Complete current 7-plugin batch (~105 tasks, ~50+ expected entries)
2. Merge score>0 entries into canonical, upload to HF
3. Run larger batches per plugin (50-100 seeds each) for volume
4. Target: 200+ diverse LIVEWEB entries across all plugins for v2.3
5. Monitor: if specific plugins consistently fail, skip and focus on working ones
