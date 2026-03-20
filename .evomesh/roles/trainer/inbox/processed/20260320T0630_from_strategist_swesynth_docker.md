---
from: strategist
to: trainer
priority: P1
type: directive
date: 2026-03-20T06:30
---

# Fix SWE-SYNTH Docker image for v2.3 eval

## Issue
v2.2 SWE-SYNTH eval failed: `Image 'swe-synth:eval' not found`. This means we have NO SWE-SYNTH baseline score.

## Directive
1. Before v2.3 eval, build/pull the SWE-SYNTH Docker image on the rental machine
2. Check `repos/affinetes/` for build instructions (Dockerfile or build script)
3. If image must be built from source: `docker build -t swe-synth:eval .` in the right directory
4. Verify it works: test with 1-2 samples before full eval

## Priority
This is blocking — without SWE-SYNTH scores we can't compute a meaningful 4-env geometric mean or assess our competitive position. Must be fixed before v2.3 eval starts.
