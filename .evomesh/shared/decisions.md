# Shared Decisions — affine-forge

Append-only log of cross-role decisions.

---

## 2026-03-17: Inherited decisions from pre-evomesh prompts

1. **NAVWORLD v9 replaces v8** — v8 NAVWORLD data (605 entries) is invalid (AMAP key expired, 100% empty tool returns). v9 (742+ entries, 100% real POI) must be used for all future training.
2. **Distillation model: DashScope qwen3-max only** — DeepSeek and other third-party models forbidden. Exception: GAME uses programmatic bots.
3. **canonical/ is the single source of truth** for training data. One env = one file. Schema: `{"messages":[...], "env":"...", "score": float}`.
4. **LGC-v2 and PRINT frozen** — no further investment, environments being deprecated.
5. **LIVEWEB distillation paused** — DashScope models cannot complete browser tasks (0% success rate). Framework changing to standard tool calling.
