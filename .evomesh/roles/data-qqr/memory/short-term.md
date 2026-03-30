# Short-term Memory

## 2026-03-30 Session

### Canonical Status: 10782
- Started: 10006 → filtered to 9659 (cutoff code≥38) → +1123 v9a batch = 10782
- V9 batch 2 generating (new prompt, 1150 entries across 7 types)

### Quality Improvements Done
1. **QQR scoring**: all 10006 entries scored locally. avg=48.3, removed 347 (code<38)
2. **Root cause found**: single_poi Comp=15.6/25 (budget=0, tips=0). Prompt lacked these requirements
3. **Prompt fixed**: single_poi + family_study now request budget details + tips
4. **tools schema added**: all entries now have eval-matching TOOLS_SCHEMA
5. **tool_calls field fixed**: 5836 entries converted from `<tool_call>` content to OpenAI format

### v2.28 Eval Results
- ckpt200: NW 37.41
- ckpt600: NW **44.08** (NEW ALL-TIME BEST)
- 26% tasks score ≤20 — model stops tool calling too early (177s vs 280s for high-score)

### Current Generation (v9 batch 2)
| Type | Count | Prompt |
|------|-------|--------|
| single_poi | 300 | NEW (budget+tips) |
| family_study | 200 | NEW (budget+tips) |
| intercity | 200 | same |
| business | 150 | same |
| hybrid | 100 | same |
| food_tour | 100 | same |
| multiday | 100 | same |

### Files Cleaned
- Removed 101 temp files (v8*, v9a*, nw_final_*, old backups, old scores)
- Archived 16 inbox messages to processed/
- Only active files remain: v9b generating, nw_code_scores.jsonl, 1 backup
