# LIVEWEB Environment

## Key Facts
- Web interaction/browsing evaluation
- Format: free thinking + JSON action object
- Supports think tags
- Cannot evaluate locally (task_id range restriction, needs predefined task set)
- Only verifiable through leaderboard deployment

## Critical Data Problem: Everything Is Too Long
- 844 entries extracted from DDB (score >= 0.5)
- Median length: 145K chars (~36K tokens)
- At max_seq_len=8192: 0 entries usable (all truncated to conversation beginning)
- When included in v3 training (2532 entries, 20.4% share): pure noise, wasted training budget

## Data History
- DDB total: 15,844 samples, avg score 0.172 (very low)
- High quality (>= 0.7, <= 16K): only 3 entries (essentially none)
- v3: included 844 entries (3x weighted = 2532), all too long — removed in v4
- v7+: re-included with heavy filtering, ~437 entries at score >= 0.5 with length cap
- Distillation attempted but failed (framework changed from original)

## Training Inclusion
| Version | Entries | Share | Notes |
|---------|---------|-------|-------|
| v3 | 2532 (3x) | 20.4% | All too long, pure noise |
| v4 | 0 | 0% | Removed entirely |
| v7 | 437 | 9.1% | Re-included with length filter |
| v8 | 437 | 6.2% | Native tool_call format |
| v10 | 437 | 3.3% | Same entries |

## Current Best / Status
- 356 entries in canonical (all score=1.0, DDB origin)
- Leaderboard: ~14-19 points (everyone is 13-19, relatively flat)
- No local eval capability
- Score improvement hard to verify without deployment

## CRITICAL: Training Format Mismatch (discovered 2026-03-20)

`forge rental prepare-data` normalizes tool_calls by dumping raw OpenAI JSON into content:
```
assistant content: [{"id": "call_0", "type": "function", "function": {"name": "goto", ...}}]
```

But Qwen3's `apply_chat_template(tools=...)` expects native format:
```
<tool_call>
{"name": "goto", "arguments": {"url": "https://..."}}
</tool_call>
```

And the system prompt should include tool definitions in `<tools>` XML tags.

**Impact**: All 356 LIVEWEB entries trained v2.2 with WRONG format. Model learned to output raw JSON arrays instead of `<tool_call>` XML tags. At eval time, sglang `--tool-call-parser qwen` cannot parse this.

**Fix required**: `prepare-data` must pass LIVEWEB entries through `tokenizer.apply_chat_template(messages, tools=tools)` to produce Qwen3-native format. Or store canonical LIVEWEB data in Qwen3-native format directly.

**Scope**: Only affects LIVEWEB (356 entries). Other envs (GAME, NAVWORLD, SWE-SYNTH) don't use tool_calls.

## Dead Ends (attempted, not viable)

### liveweb_gen.py + liveweb_env_patched.py — REMOVED (2026-03-19)
Docker-based distillation pipeline using affinetes SDK + qwen-max. **Why it failed**:
1. **qwen-max 0% success rate** on browser tasks — generates garbage trajectories, not just low quality
2. **Heavy external dependencies**: Docker, TAOSTATS_API_KEY, COINGECKO_API_KEY, CHUTES_API_KEY for validator — fragile, expensive
3. **1229-line monkey-patch** (liveweb_env_patched.py) of upstream env.py — unmaintainable, breaks on upstream updates
4. **Task diversity problem**: eval tests diverse websites, but generation was limited to CoinGecko-style queries
5. **No local eval**: cannot verify generated data improves scores without full leaderboard deployment (~$9/run)
6. **Length problem unsolved**: real eval tasks are ~36K tokens median, seq=8192 truncates everything. `num_subtasks=1` workaround only generates trivial subtasks

### DDB extraction — PARTIALLY VIABLE (current approach)
347 entries from historical eval database, all score=1.0, fit seq=8192. **Limitations**:
- Only 114 unique seeds, 1 system prompt — low diversity
- DDB avg score 0.172 (very low), only ~437/15844 entries usable after filtering
- No new data unless more eval runs happen upstream

## Plugin Coverage Gap (discovered 2026-03-19)

Eval tests 5 plugins (34 templates), our data covers only 2:
| Plugin | Templates | Our Coverage | DDB Data? |
|--------|-----------|-------------|-----------|
| CoinGecko | 8 | **335 entries** ✓ | Yes |
| Stooq | 7 | **12 entries** (partial) | Yes |
| Weather/wttr.in | 6 | **0 entries** ✗ | No — DISABLED in prod |
| Taostats | 10 | **0 entries** ✗ | Possibly — active in eval |
| Hybrid | 3 | **0 entries** ✗ | Unknown |

**Weather plugin is DISABLED** (`DISABLED_PLUGINS: set = {"weather"}` in `liveweb_arena/plugins/__init__.py`).
No DDB data exists and cannot be generated until re-enabled upstream.

**Taostats is ACTIVE** (template IDs 20-29). DDB extraction needs `forge data dynamo.py` (doesn't exist yet).

## Pipeline Status (2026-03-20)

### liveweb_real_gen.py — Pipeline works, ALL APIs blocked

**Script features** (complete):
- Supports `--plugin` for targeting specific plugins (hackernews, taostats, etc.)
- Supports `--model`/`--base-url`/`--api-key` for any OpenAI-compatible LLM
- Saves trajectories with stop action even when validator fails
- Qwen3-native format normalization in `prepare-data` (fixed)

**API attempts and results**:
| API | Endpoint | Result |
|-----|----------|--------|
| Claude proxy (claudecode) | `api.aicodemirror.com/api/claudecode/v1` | 503 + incompatible response |
| Claude proxy (codex) | `api.aicodemirror.com/api/codex/.../v1` | 401 (key format mismatch) |
| DashScope qwen3-max | `dashscope-us.aliyuncs.com/compatible-mode/v1` | **API works** but `data_inspection_failed` on ALL web content |

**DashScope content filter**: Blocks all requests where input contains web accessibility tree content. Affects ALL plugins (not just HN). This is a fundamental limitation of DashScope.

**qwen3-max capability** (when API works):
- Simple tasks (HN summary, price lookup): 2-step completion, correct answers
- Complex tasks (cross-site comparison): fails (goto loops, never clicks detail pages)
- Function calling: works (goto, click, type, type_role, stop)
- ~10% trajectory save rate overall

### Plugin Coverage (all plugins in eval)
Eval has 8 active plugins: coingecko, stooq, taostats, hackernews, arxiv, openlibrary, openmeteo, hybrid.
Training data covers only coingecko (95%) + stooq (4%). Model is blind to 6+ plugins.

## Action Items (Priority Order)

1. ✅ **FIX prepare-data tool_call format** — DONE (`_normalize_tool_calls_qwen3()`)
2. ✅ **Add tool definitions to LIVEWEB training data** — DONE (system prompt gets `<tools>` section)
3. ⏳ **Get working API endpoint** — BLOCKED. Need user to provide uncensored OpenAI-compatible API
4. **Diversify plugin coverage** — ready to execute once API unblocked
5. **Seed-to-plugin mapping** — `--plugin` arg works, can target specific plugins
