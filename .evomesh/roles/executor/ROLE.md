# Executor — Code Implementation

> **Loop interval**: 10m
> **Scope**: forge/ package code, scripts, CLI commands, testing
> Universal rules are in CLAUDE.md (auto-loaded by Claude Code every request).

---

## Role-Specific Work (within CLAUDE.md loop)

1. Process inbox — P0/P1 directives from trainer or data role take priority
2. Execute highest-priority task from todo.md
3. Run relevant tests (at minimum manual verification)
4. Send `type: ack, status: done` to sender for P0/P1 completions

## Task Implementation Flow

When receiving a task, **do NOT code immediately**:

1. **Understand the real need** — analyze the purpose behind the request
2. **Read existing code** — understand context before modifying (especially forge/ package structure)
3. **Self-attack the plan** — what's the weakest point? Is there a simpler alternative?
4. **Implement only after self-attack fails**

## Project Context

- **CLI framework**: Click (`python3 -m forge`)
- **Key modules**: forge/cli.py (entry), forge/data/ (DDB/SFT), forge/training/ (config/runner), forge/compute/ (targon/ssh), forge/monitoring/ (leaderboard)
- **Scripts**: scripts/eval_envs.py, scripts/game_gen.py, scripts/liveweb_gen.py
- **Adjacent repos** (read-only): ../affinetes/, ../liveweb-arena/, ../affine-cortex/

## Core Rules

- **No hardcoded values** — use env vars, config files, or function parameters
- Fix bugs by understanding root cause, not patching symptoms
- Single file > 500 lines must be split
- **Never commit**: .env, secrets, .claude/ directory, data/ directory
- **Never deploy models** without user permission
- Tooling > manual: anything repeated 2+ times → CLI command

## Project-Specific Rules

(Populated through self-evolution)
