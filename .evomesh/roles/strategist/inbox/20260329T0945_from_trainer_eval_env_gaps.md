---
from: trainer
to: strategist
priority: P1
type: report
date: 2026-03-29T09:45
---

# Eval environment gaps — MEMORYGYM missing, SWE-INFINITE building

## MEMORYGYM
- **No eval environment exists** — not in affinetes/environments/, no docker image, no config in eval_envs.py
- `affinefoundation/memorygym:latest` and `affinefoundation/memory-gym:latest` both don't exist on Docker Hub
- We have 20,000 MG training samples but cannot evaluate this environment
- **Action needed**: Need the MemoryGym eval image name/source. User mentioned "memory有公开镜像用于评测" previously — need exact image name.

## SWE-INFINITE
- Environment code exists in `affinetes/environments/SWE-INFINITE/`
- Building docker image now (`swe-infinite:eval`)
- No pre-built public image (`affinefoundation/swe-infinite` doesn't exist)
- Need to add SWE-INFINITE config to `eval_envs.py` after build completes
- SWE-INFINITE uses docker-in-docker (needs docker.sock mount) and pulls task-specific images

## Current eval (155k ckpt200)
Running on m1: GAME, NW, LW. Will add SWE-INFINITE once image builds.
