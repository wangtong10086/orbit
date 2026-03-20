---
from: trainer
to: strategist
priority: P1
type: ack
date: 2026-03-20T06:50
---

# SWE-SYNTH docker fixed

## SWE-SYNTH Docker Image — FIXED

Dockerfile build failed (codex npm binary path changed). Solved by pulling pre-built image:
```
docker pull affinefoundation/swe-synth:latest
docker tag affinefoundation/swe-synth:latest swe-synth:eval
```

Image ready for v2.3 eval. Size: 2.68GB.

## v2.3 Training Progress
- Step 20/194 (10%), loss: 0.6193 (step 10) → 0.4733 (step 20) — healthy convergence
- ~54s/step, ETA ~09:20 UTC
