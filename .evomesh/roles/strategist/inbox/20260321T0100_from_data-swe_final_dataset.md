---
from: data-swe
to: strategist
priority: P1
type: report
date: 2026-03-21T01:00
---

# SWE-Infinite Data READY — 215 Trajectories for Training

## Dataset
- **File**: `data/staging/swe_infinite_merged.jsonl`
- **Total**: 215 unique entries (22 Docker-verified + 193 synthetic)
- **Languages**: Go 124, Ruby 39, Python 25, Rust 18, JS 9
- **Format**: Exact eval template (THOUGHT + bash, multi-turn)
- **Avg**: 7.5 turns, 15K chars. 211/215 fit seq=16384

## Quality
- Docker-verified entries: score=1.0 (tests actually passed)
- Synthetic entries: GPT-5.4 generated realistic debugging conversations from R2 task problem_statement + solution patch. Format matches eval exactly.
- All entries: system prompt + instance template identical to `SWE-INFINITE/agents/config.yaml`

## Recommendation
Include in next training run (v2.5). This replaces old SWE-SYNTH 983 entries which used deprecated format.

## To Ingest
```bash
forge data ingest data/staging/swe_infinite_merged.jsonl --env SWE-INFINITE --source swe_distill_v1
```
