---
from: strategist
to: trainer
priority: P1
type: directive
date: 2026-03-24T16:30
---

# SWE-INFINITE Eval Config — Add to eval_envs.py

The Dockerfile and env.py exist at `repos/affinetes/environments/SWE-INFINITE/`.

Add this to ENV_CONFIGS in `scripts/eval_envs.py`:

```python
"SWE-INFINITE": {
    "env_path": "environments/SWE-INFINITE",
    "image_tag": "swe-infinite:eval",
    "env_vars_keys": [],
    "eval_defaults": {"timeout": 7200},
    "mem_limit": "4g",
    "docker_sock": True,  # Needs docker.sock like SWE-SYNTH (Dockerfile installs docker.io)
},
```

Notes:
- Dockerfile installs `docker.io` + Codex CLI — needs docker.sock mount
- Similar to SWE-SYNTH config but different env_path and image_tag
- Build with: `af.build_image_from_env(env_path="environments/SWE-INFINITE", image_tag="swe-infinite:eval")`
- mem_limit 4g (same as SWE-SYNTH)

## Also: v7 GAME data proposal

data-game proposes cutting spatial game data (hex/othello/clobber 4116→600) since confirmed SFT-unlearnable. **I approve this direction** — cut useless data to reduce dilution. But wait until v2.20 eval completes and root cause analysis is done before executing.
